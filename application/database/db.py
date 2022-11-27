import logging
import re
from collections import Counter
from itertools import permutations
from typing import Any, Dict, List, Optional, Tuple, cast

import networkx as nx
import yaml
from application.defs import cre_defs
from application.utils import file
from flask_sqlalchemy.model import DefaultMeta
from sqlalchemy import func
from sqlalchemy.sql.expression import desc  # type: ignore
import uuid

from .. import sqla  # type: ignore

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


BaseModel: DefaultMeta = sqla.Model


def generate_uuid():
    return str(uuid.uuid4())


class Node(BaseModel):  # type: ignore

    __tablename__ = "node"
    id = sqla.Column(sqla.String, primary_key=True, default=generate_uuid)
    # ASVS or standard name,  what are we linking to
    name = sqla.Column(sqla.String)
    # which part of <name> are we linking to
    section = sqla.Column(sqla.String, nullable=True)
    # which subpart of <name> are we linking to
    subsection = sqla.Column(sqla.String)
    tags = sqla.Column(sqla.String)  # coma separated tags
    version = sqla.Column(sqla.String)
    description = sqla.Column(sqla.String)
    ntype = sqla.Column(sqla.String)

    # some external link to where this is, usually a URL with an anchor
    link = sqla.Column(sqla.String, default="")
    __table_args__ = (
        sqla.UniqueConstraint(
            name,
            section,
            subsection,
            ntype,
            description,
            version,
            name="uq_node",
        ),
    )


class CRE(BaseModel):  # type: ignore

    __tablename__ = "cre"
    id = sqla.Column(sqla.String, primary_key=True, default=generate_uuid)

    external_id = sqla.Column(sqla.String, default="")
    description = sqla.Column(sqla.String, default="")
    name = sqla.Column(sqla.String)
    tags = sqla.Column(sqla.String, default="")  # coma separated tags

    __table_args__ = (
        sqla.UniqueConstraint(name, external_id, name="unique_cre_fields"),
    )


class InternalLinks(BaseModel):  # type: ignore
    # model cre-groups linking cres
    __tablename__ = "cre_links"
    type = sqla.Column(sqla.String, default="SAME")

    group = sqla.Column(
        sqla.String,
        sqla.ForeignKey("cre.id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    cre = sqla.Column(
        sqla.String,
        sqla.ForeignKey("cre.id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    __table_args__ = (
        sqla.UniqueConstraint(
            group,
            cre,
            name="uq_pair",
        ),
    )


class Links(BaseModel):  # type: ignore

    __tablename__ = "cre_node_links"
    type = sqla.Column(sqla.String, default="SAME")
    cre = sqla.Column(
        sqla.String,
        sqla.ForeignKey("cre.id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    node = sqla.Column(
        sqla.String,
        sqla.ForeignKey("node.id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    __table_args__ = (
        sqla.UniqueConstraint(
            cre,
            node,
            name="uq_pair",
        ),
    )


class CRE_Graph:
    graph: nx.Graph = None
    __instance = None

    @classmethod
    def instance(cls, session):
        if cls.__instance is None:
            cls.__instance = cls.__new__(cls)
            cls.graph = cls.load_cre_graph(session)
        return cls.__instance

    def __init__(sel):
        raise ValueError("CRE_Graph is a singleton, please call instance() instead")

    def add_edge(self, *args, **kwargs):
        return self.graph.add_edge(*args, **kwargs)

    def add_node(self, *args, **kwargs):
        return self.graph.add_node(*args, **kwargs)

    @classmethod
    def add_cre(cls, dbcre: CRE, graph: nx.DiGraph) -> nx.DiGraph:
        if dbcre:
            graph.add_node(
                f"CRE: {dbcre.id}", internal_id=dbcre.id, external_id=dbcre.external_id
            )
        else:
            logger.error("Called with dbcre being none")
        return graph

    @classmethod
    def add_dbnode(cls, dbnode: Node, graph: nx.DiGraph) -> nx.DiGraph:
        if dbnode:
            graph.add_node(
                "Node: " + str(dbnode.id),
                internal_id=dbnode.id,
                name=dbnode.name,
                section=dbnode.section,
            )
        else:
            logger.error("Called with dbnode being none")
        return graph

    @classmethod
    def load_cre_graph(cls, session) -> nx.Graph:

        graph = nx.DiGraph()
        for il in session.query(InternalLinks).all():
            group = session.query(CRE).filter(CRE.id == il.group).first()
            if not group:
                logger.error(f"CRE {il.group} does not exist?")
            graph = cls.add_cre(dbcre=group, graph=graph)

            cre = session.query(CRE).filter(CRE.id == il.cre).first()
            if not cre:
                logger.error(f"CRE {il.cre} does not exist?")
            graph = cls.add_cre(dbcre=cre, graph=graph)

            graph.add_edge(f"CRE: {il.group}", f"CRE: {il.cre}", ltype=il.type)

        for lnk in session.query(Links).all():
            node = session.query(Node).filter(Node.id == lnk.node).first()
            if not node:
                logger.error(f"Node {lnk.node} does not exist?")
            graph = cls.add_dbnode(dbnode=node, graph=graph)

            cre = session.query(CRE).filter(CRE.id == lnk.cre).first()
            graph = cls.add_cre(dbcre=cre, graph=graph)

            graph.add_edge(f"CRE: {lnk.cre}", f"Node: {str(lnk.node)}", ltype=lnk.type)
        return graph


class Node_collection:
    graph: nx.Graph = None
    session = sqla.session

    def __init__(self) -> None:
        self.graph = CRE_Graph.instance(sqla.session)
        # self.graph = CRE_Graph.instance(session=sqla.session)
        self.session = sqla.session

    def __get_external_links(self) -> List[Tuple[CRE, Node, str]]:
        external_links: List[Tuple[CRE, Node, str]] = []

        all_links = self.session.query(Links).all()
        for link in all_links:
            cre = self.session.query(CRE).filter(CRE.id == link.cre).first()
            node: Node = self.session.query(Node).filter(Node.id == link.node).first()
            external_links.append((cre, node, link.type))
        return external_links

    def __get_internal_links(self) -> List[Tuple[CRE, CRE, str]]:

        internal_links = []
        all_internal_links = self.session.query(InternalLinks).all()
        for il in all_internal_links:
            group = self.session.query(CRE).filter(CRE.id == il.group).first()
            cre = self.session.query(CRE).filter(CRE.id == il.cre).first()
            internal_links.append((group, cre, il.type))
        return internal_links

    def __get_unlinked_nodes(self) -> List[Node]:

        linked_nodes = (
            self.session.query(Node.id).join(Links).filter(Node.id == Links.node)
        )
        nodes: List[Node] = (
            self.session.query(Node).filter(Node.id.notin_(linked_nodes)).all()
        )
        return nodes

    def __get_unlinked_cres(self) -> List[CRE]:
        internally_linked_cres = self.session.query(CRE.id).join(
            InternalLinks,
            sqla.or_(InternalLinks.group == CRE.id, InternalLinks.cre == CRE.id),
        )
        externally_linked_cres = (
            self.session.query(CRE.id).join(Links).filter(Links.cre == CRE.id)
        )

        cres = (
            self.session.query(CRE)
            .filter(
                CRE.id.notin_(internally_linked_cres),
                CRE.id.notin_(externally_linked_cres),
            )
            .all()
        )
        return cres

    def __introduces_cycle(self, node_from: str, node_to: str) -> Any:
        try:
            existing_cycle = nx.find_cycle(self.graph.graph)
            if existing_cycle:
                logger.fatal(
                    "Existing graph contains cycle,"
                    "this not a recoverable error,"
                    f" manual database actions are required {existing_cycle}"
                )
                raise ValueError(
                    "Existing graph contains cycle,"
                    "this not a recoverable error,"
                    f" manual database actions are required {existing_cycle}"
                )
        except nx.exception.NetworkXNoCycle:
            pass  # happy path, we don't want cycles
        new_graph = self.graph.graph.copy()
        new_graph.add_edge(node_from, node_to)
        try:
            return nx.find_cycle(new_graph)
        except nx.NetworkXNoCycle:
            return False

    @classmethod
    def object_select(cls, node: Node, skip_attributes: List = []) -> List[Node]:
        if not node:
            return []
        qu = Node.query.filter()

        for vk, v in vars(node).items():
            if vk not in skip_attributes and hasattr(Node, vk):
                if v:
                    attr = getattr(Node, vk)
                    qu = qu.filter(attr == v)
            else:
                logger.debug(f"{vk} not in Node")
        return qu.all()

    def get_node_names(
        self, ntype: str = cre_defs.Standard.__name__
    ) -> List[Tuple[str, str]]:

        q = self.session.query(Node.ntype, Node.name).distinct().all()
        if q:
            return [i for i in q]
        return []

    def get_max_internal_connections(self) -> int:
        q = self.session.query(InternalLinks).all()
        grp_count = Counter([x.group for x in q]) or {0: 0}
        cre_count = Counter([x.cre for x in q]) or {0: 0}
        return max([max(cre_count.values()), max(grp_count.values())])

    def find_cres_of_cre(self, cre: CRE) -> Optional[List[CRE]]:
        """returns the higher level CREs of the cre or none
        if no higher level cres link to it"""
        cre_id = self.session.query(CRE.id).filter(CRE.name == cre.name).first()
        links = (
            self.session.query(InternalLinks).filter(InternalLinks.cre == cre_id).all()
        )
        if links:
            result = []
            for link in links:
                result.append(
                    self.session.query(CRE).filter(CRE.id == link.group).first()
                )
            return result

        return None

    def find_cres_of_node(self, node: cre_defs.Node) -> Optional[List[CRE]]:
        """returns the CREs that link to this node or none
        if none link to it"""
        if not node.id:
            if "subsection" not in vars(node):
                node.subsection = ""
            if "section" not in vars(node):
                node.section = ""
            if "version" not in vars(node):
                node.version = ""
            node = (
                self.session.query(Node)
                .filter(
                    sqla.and_(
                        Node.name == node.name,
                        Node.section == node.section,
                        Node.subsection == node.subsection,
                        Node.version == node.version,
                        Node.ntype == type(node).__name__,
                    )
                )
                .first()
            )
        if not node:
            return None

        result: List[CRE] = []
        for link in self.session.query(Links).filter(Links.node == node.id).all():
            result.append(self.session.query(CRE).filter(CRE.id == link.cre).first())
        return result or None

    def get_by_tags(self, tags: List[str]) -> List[cre_defs.Document]:
        """Returns the cre_defs.Documents and their Links
        that are tagged with ALL of the tags provided
        """
        # TODO: (spyros), when we have useful tags this needs to be refactored
        #  so both standards and CREs become the same query
        #  and it gets paginated
        nodes_where_clause = []
        cre_where_clause = []
        documents = []

        if not tags:
            return []

        for tag in tags:
            nodes_where_clause.append(sqla.and_(Node.tags.like("%{}%".format(tag))))
            cre_where_clause.append(sqla.and_(CRE.tags.like("%{}%".format(tag))))

        nodes = Node.query.filter(*nodes_where_clause).all() or []
        for node in nodes:
            node = self.get_nodes(
                name=node.name,
                section=node.section,
                subsection=node.subsection,
                version=node.version,
                link=node.link,
                ntype=node.ntype,
            )
            if node:
                documents.extend(node)
            else:
                logger.fatal(
                    "db.get_node returned None for"
                    "Node %s:%s that exists, BUG!" % (node.name, node.section)
                )

        cres = CRE.query.filter(*cre_where_clause).all() or []
        for c in cres:
            cre = self.get_CREs(external_id=c.external_id, name=c.name)[0]
            if cre:
                documents.append(cre)
            else:
                logger.fatal(
                    "db.get_CRE returned None for CRE %s:%s that exists, BUG!"
                    % (c.id, c.name)
                )
        return documents

    def get_nodes_with_pagination(
        self,
        name: str,
        section: Optional[str] = None,
        subsection: Optional[str] = None,
        link: Optional[str] = None,
        version: Optional[str] = None,
        partial: Optional[bool] = False,
        page: int = 0,
        items_per_page: Optional[int] = None,
        include_only: Optional[List[str]] = None,
        ntype: str = cre_defs.Standard.__name__,
        description: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[List[cre_defs.Standard]], Optional[List[Node]]]:
        """
        Returns the relevant node entries of a singular ntype (or ntype irrelevant if ntype==None) and their linked CREs
        include_only: If set, only the CRE ids in the list provided will be returned
        If a standard entry is not linked to by a CRE in the list the Standard entry will be returned empty.
        """
        nodes = []

        dbnodes = self.__get_nodes_query__(
            name=name,
            section=section,
            subsection=subsection,
            link=link,
            version=version,
            partial=partial,
            ntype=ntype,
            description=description,
        ).paginate(int(page), items_per_page, False)
        total_pages = dbnodes.pages
        if dbnodes.items:
            for dbnode in dbnodes.items:
                node = nodeFromDB(dbnode=dbnode)
                linked_cres = Links.query.filter(Links.node == dbnode.id).all()
                for dbcre_link in linked_cres:
                    dbcre = CRE.query.filter(CRE.id == dbcre_link.cre).first()
                    if dbcre:
                        if not include_only or (
                            include_only
                            and (
                                dbcre.external_id in include_only
                                or dbcre.name in include_only
                            )
                        ):
                            node.add_link(
                                cre_defs.Link(
                                    ltype=cre_defs.LinkTypes.from_str(dbcre_link.type),
                                    document=CREfromDB(dbcre),
                                )
                            )
                nodes.append(node)

            return total_pages, nodes, dbnodes
        else:
            logger.warning(f"Node {name} of type {ntype} does not exist in the db")
            return None, None, None

    # TODO(spyros): merge with above and make "paginate" a boolean switch
    def get_nodes(
        self,
        name: Optional[str] = None,
        section: Optional[str] = None,
        subsection: Optional[str] = None,
        link: Optional[str] = None,
        version: Optional[str] = None,
        partial: Optional[bool] = False,
        include_only: Optional[List[str]] = None,
        description: Optional[str] = None,
        ntype: str = cre_defs.Standard.__name__,
    ) -> Optional[List[cre_defs.Node]]:

        nodes = []
        nodes_query = self.__get_nodes_query__(
            name=name,
            section=section,
            subsection=subsection,
            link=link,
            version=version,
            partial=partial,
            ntype=ntype,
            description=description,
        )
        dbnodes = nodes_query.all()
        if dbnodes:
            for dbnode in dbnodes:
                node = nodeFromDB(dbnode=dbnode)
                linked_cres = Links.query.filter(Links.node == dbnode.id).all()
                for dbcre_link in linked_cres:
                    dbcre = CRE.query.filter(CRE.id == dbcre_link.cre).first()
                    if not dbcre:
                        logger.fatal(
                            f"CRE {dbcre_link.cre} exists in the links but not in the cre table, database corrupt?"
                        )
                    if not include_only or (
                        include_only
                        and (
                            dbcre.external_id in include_only
                            or dbcre.name in include_only
                        )
                    ):
                        node.add_link(
                            cre_defs.Link(
                                ltype=cre_defs.LinkTypes.from_str(dbcre_link.type),
                                document=CREfromDB(dbcre),
                            )
                        )
                nodes.append(node)
            return nodes
        else:
            logger.warning(
                f"Node {name} of type {ntype} and section {section} does not exist in the db"
            )

            return []

    def __get_nodes_query__(
        self,
        name: Optional[str] = None,
        section: Optional[str] = None,
        subsection: Optional[str] = None,
        link: Optional[str] = None,
        version: Optional[str] = None,
        partial: Optional[bool] = False,
        ntype: Optional[str] = None,
        description: Optional[str] = None,
    ) -> sqla.Query:
        if (
            not name
            and not section
            and not subsection
            and not link
            and not version
            and not description
        ):
            raise ValueError("tried to retrieve node with no values")
        query = Node.query
        if name:
            if not partial:
                query = Node.query.filter(func.lower(Node.name) == name.lower())
            else:
                query = Node.query.filter(func.lower(Node.name).like(name.lower()))
        if section:
            if not partial:
                query = query.filter(func.lower(Node.section) == section.lower())
            else:
                query = query.filter(func.lower(Node.section).like(section.lower()))
        if subsection:
            if not partial:
                query = query.filter(func.lower(Node.subsection) == subsection.lower())
            else:
                query = query.filter(
                    func.lower(Node.subsection).like(subsection.lower())
                )
        if link:
            if not partial:
                query = query.filter(Node.link == link)
            else:
                query = query.filter(Node.link.like(link))
        if version:
            if not partial:
                query = query.filter(Node.version == version)
            else:
                query = query.filter(Node.version.like(version))
        if ntype:
            if not partial:
                query = query.filter(Node.ntype == ntype)
            else:
                query = query.filter(Node.ntype.like(ntype))
        if description:
            if not partial:
                query = query.filter(Node.description == description)
            else:
                query = query.filter(Node.description.like(description))
        return query

    def get_CREs(
        self,
        external_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        partial: Optional[bool] = False,
        include_only: Optional[List[str]] = None,
        internal_id: Optional[str] = None,
    ) -> List[cre_defs.CRE]:
        cres: List[cre_defs.CRE] = []
        query = CRE.query
        if not external_id and not name and not description and not internal_id:
            logger.error(
                "You need to search by external_id, internal_id name or description"
            )
            return []

        if external_id:
            if not partial:
                query = query.filter(CRE.external_id == external_id)
            else:
                query = query.filter(CRE.external_id.like(external_id))
        if name:
            if not partial:
                query = query.filter(func.lower(CRE.name) == name.lower())
            else:
                query = query.filter(func.lower(CRE.name).like(name.lower()))
        if description:
            if not partial:
                query = query.filter(func.lower(CRE.description) == description.lower())
            else:
                query = query.filter(
                    func.lower(CRE.description).like(description.lower())
                )
        if internal_id:
            query = CRE.query.filter(CRE.id == internal_id)

        dbcres = query.all()
        if not dbcres:
            logger.warning(
                "CRE %s:%s:%s does not exist in the db"
                % (external_id, name, description)
            )
            return []

        # todo figure a way to return both the Node
        # and the link_type for that link
        for dbcre in dbcres:
            cre = CREfromDB(dbcre)
            linked_nodes = self.session.query(Links).filter(Links.cre == dbcre.id).all()
            for ls in linked_nodes:
                nd = self.session.query(Node).filter(Node.id == ls.node).first()
                if not include_only or (include_only and nd.name in include_only):
                    cre.add_link(
                        cre_defs.Link(
                            document=nodeFromDB(nd),
                            ltype=cre_defs.LinkTypes.from_str(ls.type),
                        )
                    )
            # todo figure the query to merge the following two
            internal_links = (
                self.session.query(InternalLinks)
                .filter(
                    sqla.or_(
                        InternalLinks.cre == dbcre.id, InternalLinks.group == dbcre.id
                    )
                )
                .all()
            )
            for il in internal_links:
                q = self.session.query(CRE)

                res: CRE
                ltype = cre_defs.LinkTypes.from_str(il.type)

                if il.cre == dbcre.id:
                    res = q.filter(CRE.id == il.group).first()
                    # if this CRE is the lower level cre the relationship will be tagged "Contains"
                    # in that case the implicit relationship is "Is Part Of"
                    # otherwise the relationship will be "Related" and we don't need to do anything
                    if ltype == cre_defs.LinkTypes.Contains:
                        # important, this is the only implicit link we have for now
                        ltype = cre_defs.LinkTypes.PartOf
                elif il.group == dbcre.id:
                    res = q.filter(CRE.id == il.cre).first()
                    ltype = cre_defs.LinkTypes.from_str(il.type)
                cre.add_link(cre_defs.Link(document=CREfromDB(res), ltype=ltype))
            cres.append(cre)
        return cres

    def export(self, dir: str = None, dry_run: bool = False) -> List[cre_defs.Document]:
        """Exports the database to a CRE file collection on disk"""
        docs: Dict[str, cre_defs.Document] = {}
        cre, standard = None, None

        # internal links are Group/HigherLevelCRE -> CRE
        for group, cre, type in self.__get_internal_links():
            grp = None
            # when cres link to each other it's a two way link
            # so handle cre1(group) -> cre2 link first
            if group.name in docs.keys():
                grp = docs[group.name]
            else:
                grp = CREfromDB(group)
            grp.add_link(
                cre_defs.Link(
                    ltype=cre_defs.LinkTypes.from_str(type), document=CREfromDB(cre)
                )
            )
            docs[group.name] = grp

            # then handle cre2 -> cre1 link
            if cre.name in docs.keys():
                c = docs[cre.name]
            else:
                c = CREfromDB(cre)
            docs[cre.name] = c
            # this cannot be grp, grp already has a link to cre2
            c.add_link(
                cre_defs.Link(
                    ltype=cre_defs.LinkTypes.from_str(type), document=CREfromDB(group)
                )
            )

        # external links are CRE -> standard
        for internal_doc, standard, type in self.__get_external_links():
            cr = None
            grp = None
            if internal_doc.name in docs.keys():
                cr = docs[internal_doc.name]
            else:
                cr = CREfromDB(internal_doc)
            if len(standard.name) != 0:
                docs[cr.name] = cr.add_link(
                    cre_defs.Link(
                        ltype=cre_defs.LinkTypes.from_str(type),
                        document=nodeFromDB(standard),
                    )
                )
        # unlinked cres next
        for ucre in self.__get_unlinked_cres():
            docs[ucre.name] = CREfromDB(ucre)

        # unlinked nodes last
        for unode in self.__get_unlinked_nodes():
            nde = nodeFromDB(unode)
            docs["%s-%s:%s:%s" % (nde.name, nde.doctype, nde.id, nde.description)] = nde
            logger.info(f"{nde.name} is unlinked?")

        if not dry_run:
            for _, doc in docs.items():
                title = (
                    doc.name.replace("/", "-")
                    .replace(" ", "_")
                    .replace('"', "")
                    .replace("'", "")
                    + ".yaml"
                )
                file.writeToDisk(
                    file_title=title,
                    file_content=yaml.safe_dump(doc.todict()),
                    cres_loc=dir,
                )

        return list(docs.values())

    def add_cre(self, cre: cre_defs.CRE) -> CRE:
        entry: CRE
        query: sqla.Query = self.session.query(CRE).filter(
            func.lower(CRE.name) == cre.name.lower()
        )
        if cre.id:
            entry = query.filter(CRE.external_id == cre.id).first()
        else:
            entry = query.filter(
                func.lower(CRE.description) == cre.description.lower()
            ).first()

        if entry is not None:
            logger.debug("knew of %s ,updating" % cre.name)
            if not entry.external_id:
                if entry.external_id != cre.id:
                    raise ValueError(
                        f"Attempting to register existing CRE"
                        f"{entry.external_id}:{entry.name} with other ID {cre.id}"
                    )
                entry.external_id = cre.id
            if not entry.description:
                entry.description = cre.description
            if not entry.tags:
                entry.tags = ",".join(cre.tags)
            return entry
        else:
            logger.debug("did not know of %s ,adding" % cre.name)
            entry = CRE(
                description=cre.description,
                name=cre.name,
                external_id=cre.id,
                tags=",".join([str(t) for t in cre.tags]),
            )
            self.session.add(entry)
            self.session.commit()
            self.graph = self.graph.add_cre(dbcre=entry, graph=self.graph)
        return entry

    def add_node(self, node: cre_defs.Node) -> Optional[Node]:
        dbnode = dbNodeFromNode(node)
        if not dbnode:
            logger.warning(f"{node} could not be transformed to a DB object")
            return None
        if not dbnode.ntype:
            logger.warning(f"{node} has no registered type, cannot add, skipping")
            return None

        entries = self.object_select(dbnode, skip_attributes=["link"])
        if entries:
            entry = entries[0]

            logger.debug(f"knew of {entry.name}:{entry.section}:{entry.link} ,updating")
            entry.link = node.hyperlink
            self.session.commit()
            return entry
        else:
            logger.debug(f"did not know of {dbnode.name}:{dbnode.section} ,adding")
            self.session.add(dbnode)
            self.session.commit()

            self.graph = self.graph.add_dbnode(dbnode=dbnode, graph=self.graph)
        return dbnode

    def add_internal_link(
        self, group: CRE, cre: CRE, type: cre_defs.LinkTypes = cre_defs.LinkTypes.Same
    ) -> None:

        if cre.id is None:
            if cre.external_id is None:
                cre = (
                    self.session.query(CRE)
                    .filter(
                        sqla.and_(
                            CRE.name == cre.name, CRE.description == cre.description
                        )
                    )
                    .first()
                )
            else:
                cre = (
                    self.session.query(CRE)
                    .filter(
                        sqla.and_(
                            CRE.name == cre.name, CRE.external_id == cre.external_id
                        )
                    )
                    .first()
                )
        if group.id is None:
            if group.external_id is None:
                group = (
                    self.session.query(CRE)
                    .filter(
                        sqla.and_(
                            CRE.name == group.name, CRE.description == group.description
                        )
                    )
                    .first()
                )
            else:
                group = (
                    self.session.query(CRE)
                    .filter(
                        sqla.and_(
                            CRE.name == group.name, CRE.external_id == group.external_id
                        )
                    )
                    .first()
                )
        if cre is None or group is None:
            logger.fatal(
                "Tried to insert internal mapping with element"
                " that doesn't exist in db, this looks like a bug"
            )
            return None

        entry = (
            self.session.query(InternalLinks)
            .filter(
                sqla.or_(
                    sqla.and_(
                        InternalLinks.cre == group.id, InternalLinks.group == cre.id
                    ),
                    sqla.and_(
                        InternalLinks.cre == cre.id, InternalLinks.group == group.id
                    ),
                )
            )
            .first()
        )
        if entry is not None:
            logger.debug(
                f"knew of internal link {cre.name} == {group.name} of type {entry.type},updating to type {type.value}"
            )
            entry.type = type.value
            self.session.commit()

            return None

        else:
            logger.debug(
                "did not know of internal link"
                f" {group.external_id}:{group.name}"
                f" == {cre.external_id}:{cre.name} ,adding"
            )
            cycle = self.__introduces_cycle(f"CRE: {group.id}", f"CRE: {cre.id}")
            if not cycle:
                self.session.add(
                    InternalLinks(type=type.value, cre=cre.id, group=group.id)
                )
                self.session.commit()
                self.graph.add_edge(
                    f"CRE: {group.id}", f"CRE: {cre.id}", ltype=type.value
                )
            else:
                logger.warning(
                    f"A link between CREs {group.external_id}-{group.name} and"
                    f" {cre.external_id}-{cre.name} "
                    f"would introduce cycle {cycle}, skipping"
                )

    def add_link(
        self,
        cre: CRE,
        node: Node,
        type: cre_defs.LinkTypes = cre_defs.LinkTypes.Same,
    ) -> None:

        if cre.id is None:
            cre = (
                self.session.query(CRE).filter(sqla.and_(CRE.name == cre.name)).first()
            )
        if node.id is None:
            node = self.object_select(node=node)[0]

        entry = (
            self.session.query(Links)
            .filter(sqla.and_(Links.cre == cre.id, Links.node == node.id))
            .first()
        )
        if entry:
            logger.debug(
                f"knew of link {node.name}:{node.section}"
                f"=={cre.name} of type {entry.type},"
                f"updating type to {type.value}"
            )
            entry.type = type.value
            self.session.commit()
            return
        else:
            cycle = self.__introduces_cycle(
                f"CRE: {cre.id}", f"Standard: {str(node.id)}"
            )
            if not cycle:
                logger.debug(
                    f"did not know of link {node.id})"
                    f"{node.name}:{node.section}=={cre.id}){cre.name}"
                    " ,adding"
                )
                self.session.add(Links(type=type.value, cre=cre.id, node=node.id))
                self.graph.add_edge(
                    f"CRE: {cre.id}", f"Node: {str(node.id)}", ltype=type.value
                )
            else:
                logger.warning(
                    f"A link between CRE {cre.external_id}"
                    f" and Node: {node.name}"
                    f":{node.section}:{node.subsection}"
                    f" would introduce cycle {cycle}, skipping"
                )
                logger.debug(f"{cycle}")
        self.session.commit()

    def find_path_between_nodes(
        self, node_source_id: int, node_destination_id: int
    ) -> bool:
        """One line method to return paths in a graph,
        this starts getting complicated when we have more linktypes"""
        res: bool = nx.has_path(
            self.graph.graph.to_undirected(),
            "Node: " + str(node_source_id),
            "Node: " + str(node_destination_id),
        )

        return res

    def gap_analysis(self, node_names: List[str]) -> List[cre_defs.Node]:
        """Since the CRE structure is a tree-like graph with
        leaves being nodes we can find the paths between nodes
        find_path_between_nodes() is a graph-path-finding method
        """
        processed_nodes = []
        dbnodes: List[Node] = []
        for name in node_names:
            dbnodes.extend(self.session.query(Node).filter(Node.name == name).all())

        for node in dbnodes:
            working_node = nodeFromDB(node)
            for other_node in dbnodes:
                if node.id == other_node.id:
                    continue
                if self.find_path_between_nodes(node.id, other_node.id):
                    working_node.add_link(
                        cre_defs.Link(
                            ltype=cre_defs.LinkTypes.LinkedTo,
                            document=nodeFromDB(other_node),
                        )
                    )
            processed_nodes.append(working_node)
        return processed_nodes

    def text_search(self, text: str) -> List[Optional[cre_defs.Document]]:
        """Given a piece of text, tries to find the best match
        for the text in the database.
        Shortcuts:
           'CRE:<id>' will search for the <id> in cre external ids
           'CRE:<name>' will search for the <name> in cre names
           '<Node type e.g. Standard>:<name>[:<section>:<subsection>:<hyperlink>]' will search for
               all entries of <name> and optionally, section/subsection
           '\d\d\d-\d\d\d' (two sets of 3 digits) will first try to match
                CRE ids before it performs a free text search
           Anything else will be a case insensitive LIKE query in the database
        """
        # structured text search first
        cre_id_search = r"CRE(:| )(?P<id>\d+-\d+)"
        cre_naked_id_search = r"\d\d\d-\d\d\d"
        cre_name_search = r"CRE(:| )(?P<name>\w+)"
        types = "|".join([v.value for v in cre_defs.Credoctypes])
        node_search = (
            r"(Node|(?P<ntype>"
            + types
            + "))?((:| )?(?P<link>https?://\S+))?((:| )(?P<val>.+$))?"
        )
        match = re.search(cre_id_search, text, re.IGNORECASE)
        if match:
            return self.get_CREs(external_id=match.group("id"))

        match = re.search(cre_naked_id_search, text, re.IGNORECASE)
        if match:
            return self.get_CREs(external_id=match.group())

        match = re.search(cre_name_search, text, re.IGNORECASE)
        if match:
            return self.get_CREs(name=match.group("name"))

        match = re.search(node_search, text, re.IGNORECASE)
        if match:
            link = match.group("link")
            ntype = match.group("ntype")
            txt = match.group("val")
            results: List[cre_defs.Document] = []
            if txt:
                args = txt.split(":") if ":" in txt else txt.split(" ")
                if len(args) < 3:
                    args += [""] * (3 - len(args))
                s = set([p for p in permutations(args, 3)])
                for combo in s:
                    nodes = self.get_nodes(
                        name=combo[0],
                        section=combo[1],
                        subsection=combo[2],
                        link=link,
                        ntype=ntype,
                    )
                    if nodes:
                        results.extend(nodes)
            elif link or ntype:
                nodes = self.get_nodes(link=link, ntype=ntype)
                if nodes:
                    results.extend(nodes)
            if results:
                return list(set(results))
        # fuzzy matches second
        args = [f"%{text}%", "", "", "", ""]
        results = []
        s = set([p for p in permutations(args, 5)])
        for combo in s:
            nodes = self.get_nodes(
                name=combo[0],
                section=combo[1],
                subsection=combo[2],
                link=combo[3],
                description=combo[4],
                partial=True,
                ntype=None,  # type: ignore
            )
            if nodes:
                results.extend(nodes)
        args = [f"%{text}%", None, None]
        for combo in permutations(args, 3):
            cres = self.get_CREs(
                name=combo[0], external_id=combo[1], description=combo[2], partial=True
            )
            if cres:
                results.extend(cres)
        return list(set(results))

    def get_root_cres(self):
        """Returns CRES that only have "Contains" links
        Implemented via filtering graph nodes whose incoming edges are only "RELATED" type links
        """

        def node_is_root(node):
            return node.startswith("CRE") and (
                self.graph.graph.in_degree(node) == 0
                or not [
                    edge
                    for edge in self.graph.graph.in_edges(node)
                    if self.graph.graph.get_edge_data(*edge)["ltype"]
                    != cre_defs.LinkTypes.Related.value
                ]
            )  # there are no incoming edges with relationships other than RELATED

        nodes = filter(node_is_root, self.graph.graph.nodes)

        result = []
        for nodeid in nodes:
            result.extend(
                self.get_CREs(internal_id=self.graph.graph.nodes[nodeid]["internal_id"])
            )
        return result


def dbNodeFromNode(doc: cre_defs.Node) -> Optional[Node]:
    if doc.doctype == cre_defs.Credoctypes.Standard:
        return dbNodeFromStandard(doc)
    elif doc.doctype == cre_defs.Credoctypes.Code:
        return dbNodeFromCode(doc)
    elif doc.doctype == cre_defs.Credoctypes.Tool:
        return dbNodeFromTool(doc)
    else:
        return None


def dbNodeFromCode(code: cre_defs.Node) -> Node:
    code = cast(cre_defs.Code, code)
    tags = ""
    if code.tags:
        tags = ",".join(tags)
    return Node(
        name=code.name,
        ntype=code.doctype.value,
        tags=tags,
        description=code.description,
        link=code.hyperlink,
    )


def dbNodeFromStandard(standard: cre_defs.Node) -> Node:
    standard = cast(cre_defs.Standard, standard)
    tags = ""
    if standard.tags:
        tags = ",".join(standard.tags)
    return Node(
        name=standard.name,
        ntype=standard.doctype.value,
        tags=tags,
        description=standard.description,
        link=standard.hyperlink,
        section=standard.section,
        subsection=standard.subsection,
        version=standard.version,
    )


def dbNodeFromTool(tool: cre_defs.Node) -> Node:
    tool = cast(cre_defs.Tool, tool)
    tgs = [tool.tooltype.value]
    if tool.tags:
        tgs.extend(tool.tags)
    tags = ",".join(tgs)
    return Node(
        name=tool.name,
        tags=tags,
        ntype=tool.doctype.value,
        description=tool.description,
        link=tool.hyperlink,
        section=tool.ruleID,
    )


def nodeFromDB(dbnode: Node) -> cre_defs.Node:
    tags = []
    if dbnode.tags:
        tags = list(set(dbnode.tags.split(",")))
    if dbnode.ntype == cre_defs.Standard.__name__:
        return cre_defs.Standard(
            name=dbnode.name,
            section=dbnode.section,
            subsection=dbnode.subsection,
            hyperlink=dbnode.link,
            tags=tags,
            version=dbnode.version,
        )
    elif dbnode.ntype == cre_defs.Tool.__name__:
        ttype = cre_defs.ToolTypes.Unknown
        for tag in tags:
            if tag in cre_defs.ToolTypes:
                ttype = cre_defs.ToolTypes[tag]
                tags.remove(tag)
        return cre_defs.Tool(
            name=dbnode.name,
            hyperlink=dbnode.link,
            tags=tags,
            description=dbnode.description,
            tooltype=ttype,
            ruleID=dbnode.section,
        )
    elif dbnode.ntype == cre_defs.Code.__name__:
        return cre_defs.Code(
            name=dbnode.name,
            hyperlink=dbnode.link,
            tags=tags,
            description=dbnode.description,
        )
    else:
        raise ValueError(
            f"Db node {dbnode.name} has an unrecognised ntype {dbnode.ntype}"
        )


def CREfromDB(dbcre: CRE) -> cre_defs.CRE:
    tags = []
    if dbcre.tags:
        tags = list(set(dbcre.tags.split(",")))
    return cre_defs.CRE(
        name=dbcre.name, description=dbcre.description, id=dbcre.external_id, tags=tags
    )


def dbCREfromCRE(cre: cre_defs.CRE) -> CRE:
    tags = cre.tags if cre.tags else []
    return CRE(
        name=cre.name,
        description=cre.description,
        external_id=cre.id,
        tags=",".join(tags),
    )
