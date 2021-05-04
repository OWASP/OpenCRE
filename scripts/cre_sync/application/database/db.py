

# from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.sql import operators
# from sqlalchemy.orm import sessionmaker, relationship
from enum import Enum
from collections import namedtuple
from application.defs import cre_defs
from application.utils import file
import yaml
import logging
import os
import base64

from pprint import pprint
from .. import sqla

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Standard(sqla.Model):
    __tablename__ = "standard"
    id = sqla.Column(sqla.Integer, primary_key=True)
    # ASVS or standard name,  what are we linking to
    name = sqla.Column(sqla.String)
    # which part of <name> are we linking to
    section = sqla.Column(sqla.String, nullable=False)
    # which subpart of <name> are we linking to
    subsection = sqla.Column(sqla.String)
    tags = sqla.Column(sqla.String, default="")  # coma separated tags

    # some external link to where this is, usually a URL with an anchor
    link = sqla.Column(sqla.String)
    __table_args__ = (
        sqla.UniqueConstraint(name, section, subsection,
                              name="standard_section"),
    )


class CRE(sqla.Model):
    __tablename__ = "cre"
    id = sqla.Column(sqla.Integer, primary_key=True)

    external_id = sqla.Column(sqla.String, default="")
    description = sqla.Column(sqla.String, default="")
    name = sqla.Column(sqla.String)
    tags = sqla.Column(sqla.String, default="")  # coma separated tags

    __table_args__ = (sqla.UniqueConstraint(
        name, external_id, name="unique_cre_fields"),)


class InternalLinks(sqla.Model):
    # model cre-groups linking cres
    __tablename__ = "crelinks"
    type = sqla.Column(sqla.String, default="SAM")
    group = sqla.Column(sqla.Integer, sqla.ForeignKey(
        "cre.id"), primary_key=True)
    cre = sqla.Column(sqla.Integer, sqla.ForeignKey(
        "cre.id"), primary_key=True)


class Links(sqla.Model):
    __tablename__ = "links"
    type = sqla.Column(sqla.String, default="SAM")
    cre = sqla.Column(sqla.Integer, sqla.ForeignKey(
        "cre.id"), primary_key=True)
    standard = sqla.Column(sqla.Integer, sqla.ForeignKey(
        "standard.id"), primary_key=True)


class Standard_collection:
    def __init__(self):
        self.session = sqla.session

    def __get_external_links(self):
        external_links = []
        all_links = self.session.query(Links).all()
        for link in all_links:
            cre = self.session.query(CRE).filter(CRE.id == link.cre).first()
            standard = (
                self.session.query(Standard)
                .filter(Standard.id == link.standard)
                .first()
            )
            external_links.append((cre, standard, link.type))
        return external_links

    def __get_internal_links(self):
        internal_links = []
        all_internal_links = self.session.query(InternalLinks).all()
        for il in all_internal_links:
            group = self.session.query(CRE).filter(CRE.id == il.group).first()
            cre = self.session.query(CRE).filter(CRE.id == il.cre).first()
            internal_links.append((group, cre, il.type))
        return internal_links

    def __get_unlinked_standards(self):
        linked_standards = (
            self.session.query(Standard.id)
            .join(Links)
            .filter(Standard.id == Links.standard)
        )
        return (
            self.session.query(Standard)
            .filter(Standard.id.notin_(linked_standards))
            .all()
        )

    def get_standards_names(self):
        # this returns a tuple of (str,nothing)
        q = self.session.query(Standard.name).distinct().all()
        res = [i[0] for i in q]
        return res

    def get_max_internal_connections(self):
        count = {}
        # TODO: (spyros) this should be made into a count(*) query
        q = self.session.query(InternalLinks).all()
        for il in q:
            if il.group in count.keys():
                count[il.group] += 1
            else:
                count[il.group] = 1
            if il.cre in count.keys():
                count[il.cre] += 1
            else:
                count[il.cre] = 1
        if count:
            return max(count.values())
        else:
            return 0

    def find_cres_of_cre(self, cre: CRE):
        """returns the higher level CREs of the cre or none if no higher level cres link to it"""
        cre_id = self.session.query(CRE).filter(
            CRE.name == cre.name).first().id
        links = (
            self.session.query(InternalLinks).filter(
                InternalLinks.cre == cre_id).all()
        )
        if links:
            result = []
            for link in links:
                result.append(
                    self.session.query(CRE).filter(
                        CRE.id == link.group).first()
                )
            return result

    def find_cres_of_standard(self, standard: Standard):
        db_standard = (
            self.session.query(Standard)
            .filter(
                sqla.and_(
                    Standard.name == standard.name,
                    Standard.section == standard.section,
                    Standard.subsection == standard.subsection,
                )
            )
            .first()
        )
        """ returns the CREs that link to this standard or none if none link to it"""
        if not db_standard:
            return
        links = self.session.query(Links).filter(
            Links.standard == db_standard.id).all()
        if links:
            result = []
            for link in links:
                cre = self.session.query(CRE).filter(
                    CRE.id == link.cre).first()
                result.append(cre)
            return result

    def get_by_tags(self, tags: list) -> [cre_defs.Document]:
        """Returns the cre_defs.Documents and their Links
        that are tagged with ALL of the tags provided
        """
        # TODO: (spyros), when we have useful tags this needs to be refactored so both standards and CREs become the same query and it gets paginated
        standards_where_clause = []
        cre_where_clause = []
        documents = []

        if tags == []:
            return []

        for tag in tags:
            standards_where_clause.append(
                sqla.and_(Standard.tags.like("%{}%".format(tag))))
            cre_where_clause.append(
                sqla.and_(CRE.tags.like("%{}%".format(tag))))

        standards = (
            Standard.query.filter(*standards_where_clause).all() or []
        )
        for standard in standards:
            standard = self.get_standards(
                name=standard.name,
                section=standard.section,
                subsection=standard.subsection,
                link=standard.link,
            )
            if standard:
                documents.extend(standard)
            else:
                logger.fatal(
                    "db.get_standard returned None for Standard %s:%s that exists, BUG!"
                    % (standard.name, standard.section)
                )

        cres = CRE.query.filter(*cre_where_clause).all() or []
        for c in cres:
            cre = self.get_CRE(external_id=c.external_id, name=c.name)
            if cre:
                documents.append(cre)
            else:
                logger.fatal(
                    "db.get_CRE returned None for CRE %s:%s that exists, BUG!"
                    % (c.id, c.name)
                )
        return documents

    def get_standards(self, name: str, section=None, subsection=None, link=None, page: int = 0, items_per_page=None):
        standards = []
        query = Standard.query.filter(Standard.name == name)
        if section:
            query = query.filter(Standard.section == section)
        if subsection:
            query = query.filter(Standard.subsection == subsection)
        if link:
            query = query.filter(Standard.link == link)
        if int(page) > 0 and items_per_page:
            dbstands = query.paginate(int(page), items_per_page, False).items
        else:
            dbstands = query.all()
        if dbstands:
            for dbstand in dbstands:
                standard = StandardFromDB(dbstandard=dbstand)
                linked_cres = (
                    Links.query.filter(Links.standard == dbstand.id).all()
                )
                for dbcre_link in linked_cres:
                    standard.add_link(
                        cre_defs.Link(
                            ltype=dbcre_link.type,
                            document=CREfromDB(
                                CRE.query
                                .filter(CRE.id == dbcre_link.cre)
                                .first()
                            ),
                        )
                    )
                standards.append(standard)
        else:
            logger.warning("Standard %s does not exist in the db" % (name))
            return
        return standards

    def get_CRE(self, external_id: str = None, name: str = None) -> cre_defs.CRE:
        cre = None
        query = CRE.query
        if external_id:
            query = query.filter(CRE.external_id == external_id)
        if name:
            query = query.filter(CRE.name == name)

        dbcre = query.first()
        if dbcre:
            cre = CREfromDB(dbcre)
        else:
            logger.warning("CRE %s:%s does not exist in the db" %
                           (external_id, name))
            return

        # todo figure a way to return both the Standard and the link_type for that link
        linked_standards = self.session.query(
            Links).filter(Links.cre == dbcre.id).all()
        for ls in linked_standards:
            cre.add_link(
                cre_defs.Link(
                    document=StandardFromDB(
                        self.session.query(Standard)
                        .filter(Standard.id == ls.standard)
                        .first()
                    ),
                    ltype=cre_defs.LinkTypes.from_str(ls.type),
                )
            )

        # todo figure the query to merge the following two
        internal_links = (
            self.session.query(InternalLinks)
            .filter(sqla.or_(InternalLinks.cre == dbcre.id, InternalLinks.group == dbcre.id))
            .all()
        )
        for il in internal_links:
            # pprint(cre)
            q = self.session.query(CRE)
            res = None
            if il.cre == dbcre.id:
                res = q.filter(CRE.id == il.group).first()
            elif il.group == dbcre.id:
                res = q.filter(CRE.id == il.cre).first()
            cre.add_link(
                cre_defs.Link(
                    document=CREfromDB(res), ltype=cre_defs.LinkTypes.from_str(il.type)
                )
            )

        return cre

    def export(self, dir):
        """Exports the database to a CRE file collection on disk"""
        docs = {}
        cre, standard = None, None
        cres_written = {}

        # internal links are Group/HigherLevelCRE -> CRE
        for link in self.__get_internal_links():
            group = link[0]
            cre = link[1]
            type = link[2]
            grp = None
            # when cres link to each other it's a two way link
            # so handle cre1(group) -> cre2 link first
            if group.name in docs.keys():
                grp = docs[group.name]
            else:
                grp = CREfromDB(group)
            grp.add_link(cre_defs.Link(ltype=type, document=CREfromDB(cre)))
            docs[group.name] = grp

            # then handle cre2 -> cre1 link
            if cre.name in docs.keys():
                c = docs[cre.name]
            else:
                c = CREfromDB(cre)
            docs[cre.name] = c
            # this cannot be grp, grp already has a link to cre2
            c.add_link(cre_defs.Link(ltype=type, document=CREfromDB(group)))

        # external links are CRE -> standard
        for link in self.__get_external_links():
            internal_doc = link[0]
            standard = link[1]
            type = link[2]
            cr = None
            grp = None
            if internal_doc.name in docs.keys():
                cr = docs[internal_doc.name]
            else:
                cr = CREfromDB(internal_doc)
            if len(standard.name) != 0:
                cr.add_link(
                    cre_defs.Link(
                        ltype=type, document=StandardFromDB(standard))
                )
            docs[cr.name] = cr

        # unlinked standards last
        for ustandard in self.__get_unlinked_standards():
            ustand = StandardFromDB(ustandard)
            docs["%s-%s:%s" % (ustand.name, ustand.section,
                               ustand.subsection)] = ustand

        for _, doc in docs.items():
            title = doc.name.replace("/", "-") + ".yaml"
            file.writeToDisk(
                file_title=title,
                file_content=yaml.safe_dump(doc.todict()),
                cres_loc=dir,
            )
        return docs.values()

    def add_cre(self, cre: cre_defs.CRE):
        if cre.id != None:
            entry = (
                self.session.query(CRE)
                .filter(CRE.name == cre.name, CRE.external_id == cre.id)
                .first()
            )
        else:
            entry = (
                self.session.query(CRE)
                .filter(CRE.name == cre.name, CRE.description == cre.description)
                .first()
            )

        if entry is not None:
            logger.debug("knew of %s ,skipping" % cre.name)
            return entry
        else:
            logger.debug("did not know of %s ,adding" % cre.name)
            entry = CRE(description=cre.description,
                        name=cre.name, external_id=cre.id)
            self.session.add(entry)
            self.session.commit()
        return entry

    def add_standard(self, standard: cre_defs.Standard) -> Standard:
        entry = (
            Standard.query.filter(
                sqla.and_(
                    Standard.name == standard.name,
                    Standard.section == standard.section,
                    Standard.subsection == standard.subsection,
                )
            )
            .first()
        )
        if entry is not None:
            logger.debug("knew of %s:%s ,updating" %
                         (entry.name, entry.section))
            entry.link = standard.hyperlink
            self.session.commit()
            return entry
        else:
            logger.debug(
                "did not know of %s:%s ,adding" % (
                    standard.name, standard.section)
            )
            entry = Standard(
                name=standard.name,
                section=standard.section,
                subsection=standard.subsection,
                link=standard.hyperlink,
            )
            self.session.add(entry)
        self.session.commit()
        return entry

    def add_internal_link(self, group: CRE, cre: CRE, type: cre_defs.LinkTypes):
        if cre.id == None:
            if cre.external_id == None:
                cre = (
                    self.session.query(CRE)
                    .filter(
                        sqla.and_(CRE.name == cre.name,
                                  CRE.description == cre.description)
                    )
                    .first()
                )
            else:
                cre = (
                    self.session.query(CRE)
                    .filter(
                        sqla.and_(CRE.name == cre.name,
                                  CRE.external_id == cre.external_id)
                    )
                    .first()
                )
        if group.id == None:
            if group.external_id == None:
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
        if cre == None or group == None:
            logger.fatal(
                "Tried to insert internal mapping with element that doesn't exist in db, this looks like a bug"
            )
            return
        entry = (
            self.session.query(InternalLinks)
            .filter(
                sqla.or_(
                    sqla.and_(InternalLinks.cre == group.id,
                              InternalLinks.group == cre.id),
                    sqla.and_(InternalLinks.cre == cre.id,
                              InternalLinks.group == group.id),
                )
            )
            .first()
        )
        if entry != None:
            logger.debug(
                "knew of internal link %s == %s ,updating" % (
                    cre.name, group.name)
            )
            entry.type = type.value
            self.session.commit()
            return
        else:
            logger.debug(
                "did not know of internal link %s:%s == %s:%s ,adding"
                % (group.external_id, group.name, cre.external_id, cre.name)
            )
            self.session.add(InternalLinks(
                type=type.value, cre=cre.id, group=group.id))

    def add_link(self, cre: CRE, standard: Standard, type: cre_defs.LinkTypes):
        if cre.id == None:
            cre = self.session.query(CRE).filter(
                sqla.and_(CRE.name == cre.name)).first()
        if standard.id == None:
            standard = (
                self.session.query(Standard)
                .filter(
                    sqla.and_(
                        Standard.name == standard.name,
                        Standard.section == standard.section,
                        Standard.subsection == standard.subsection,
                    )
                )
                .first()
            )

        entry = (
            self.session.query(Links)
            .filter(sqla.and_(Links.cre == cre.id, Links.standard == standard.id))
            .first()
        )
        if entry:
            logger.debug(
                "knew of link %s:%s==%s ,updating"
                % (standard.name, standard.section, cre.name)
            )
            entry.type = type.value
            self.session.commit()
            return
        else:
            logger.debug(
                "did not know of link %s)%s:%s==%s)%s ,adding"
                % (standard.id, standard.name, standard.section, cre.id, cre.name)
            )
            self.session.add(
                Links(type=type.value, cre=cre.id, standard=standard.id))
        self.session.commit()


def StandardFromDB(dbstandard: Standard):
    tags = []
    if dbstandard.tags:
        tags = dbstandard.tags.split(",")
    return cre_defs.Standard(
        name=dbstandard.name,
        section=dbstandard.section,
        subsection=dbstandard.subsection,
        hyperlink=dbstandard.link,
        tags=tags,
    )


def CREfromDB(dbcre: CRE):
    tags = []
    if dbcre.tags:
        tags = dbcre.tags.split(",")
    return cre_defs.CRE(
        name=dbcre.name, description=dbcre.description, id=dbcre.external_id, tags=tags
    )
