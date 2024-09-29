import sys
import logging
import networkx as nx
from typing import List, Tuple
from application.defs import cre_defs as defs


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class CycleDetectedError(Exception):
    def __init__(self, message):
        super().__init__(message)


class Singleton_Graph_Storage(nx.DiGraph):
    __instance: "Singleton_Graph_Storage" = None

    @classmethod
    def instance(cls) -> "Singleton_Graph_Storage":
        if cls.__instance is None:
            cls.__instance = nx.DiGraph()
        return cls.__instance

    def __init__():
        raise ValueError("CRE_Graph is a singleton, please call instance() instead")


class CRE_Graph:
    __graph: nx.Graph = None
    __parent_child_subgraph = None

    def get_raw_graph(self):
        return self.__graph

    def with_graph(self, graph: nx.Graph, graph_data: List[defs.Document]):
        self.__graph = graph
        if not len(graph.edges):
            self.__load_cre_graph(graph_data)

    def introduces_cycle(self, doc_from: defs.Document, link_to: defs.Link):
        try:
            ex = self.has_cycle()
            if ex:
                raise ValueError(
                    "Existing graph contains cycle,"
                    "this not a recoverable error,"
                    f" manual database actions are required {ex}"
                )
        except nx.exception.NetworkXNoCycle:
            pass  # happy path, we don't want cycles

        # TODO: when this becomes too slow (e.g. when we are importing 1000s of CREs at once)
        # we can instead add the edge find the cycle and then remove the edge
        new_graph = self.__graph.copy()

        # this needs our special add_edge but with the copied graph
        new_graph = self.__add_graph_edge(
            doc_from=doc_from, link_to=link_to, graph=new_graph
        )
        try:
            return nx.find_cycle(new_graph)
        except nx.exception.NetworkXNoCycle:
            return None

    def has_cycle(self):
        try:
            ex = nx.find_cycle(self.__graph, orientation="original")
            return ex
        except nx.exception.NetworkXNoCycle:
            return None

    def get_hierarchy(self, rootIDs: List[str], creID: str):

        if len(self.__graph.edges) == 0:
            logger.error("graph is empty")
            return -1

        if creID in rootIDs:
            return 0

        if self.__parent_child_subgraph == None:
            if len(self.__graph.edges) == 0:
                raise ValueError("Graph has no edges")
            include_cres = []
            for el in self.__graph.edges:
                edge_data = self.__graph.get_edge_data(*el)
                if (
                    el[0].startswith("CRE")
                    and el[1].startswith("CRE")
                    and (
                        edge_data["ltype"] == defs.LinkTypes.Contains
                        or edge_data["ltype"] == defs.LinkTypes.PartOf
                    )
                ):
                    include_cres.append(el[0])
                    include_cres.append(el[1])

            for el in rootIDs:
                if (
                    el not in include_cres
                ):  # If the root is not in the parent/children graph, add it to prevent an error and continue, there is not path to our CRE anyway
                    include_cres.append(f"CRE: {el}")
            self.__parent_child_subgraph = self.__graph.subgraph(set(include_cres))

        shortest_path = sys.maxsize
        for root in rootIDs:
            try:
                shortest_path = min(
                    shortest_path,
                    len(
                        nx.shortest_path(
                            self.__parent_child_subgraph,
                            f"CRE: {root}",
                            f"CRE: {creID}",
                        )
                    )
                    - 1,
                )
            except nx.exception.NodeNotFound:
                # If the CRE is not in the parent/children graph it means that it's a lone CRE, so it's a root and we return 0
                if f"CRE: {root}" not in self.__graph.nodes():
                    raise ValueError(f"CRE: {root} isn't in the graph")
                if f"CRE: {creID}" not in self.__graph.nodes():
                    raise ValueError(f"CRE: {creID} isn't in the graph")
                return 0
            except nx.exception.NetworkXNoPath:
                # If there is no path to the CRE, continue
                continue
        return shortest_path

    def get_path(self, start: str, end: str) -> List[Tuple[str, str]]:
        try:
            return nx.shortest_path(self.__graph, start, end)
        except nx.NetworkXNoPath:
            return []

    def add_cre(self, cre: defs.CRE):
        if not isinstance(cre, defs.CRE):
            raise ValueError(
                f"inmemory graph add_cre takes only cre objects, instead got {type(cre)}"
            )
        graph_cre = f"{defs.Credoctypes.CRE.value}: {cre.id}"
        if cre and graph_cre not in self.__graph.nodes():
            self.__graph.add_node(graph_cre, internal_id=cre.id)

    def add_dbnode(self, dbnode: defs.Node):
        graph_node = "Node: " + str(dbnode.id)
        if dbnode and graph_node not in self.__graph.nodes():
            self.__graph.add_node(graph_node, internal_id=dbnode.id)

    def add_link(self, doc_from: defs.Document, link_to: defs.Link):
        logger.debug(
            f"adding link {doc_from.id}, {link_to.document.id} ltype: {link_to.ltype}"
        )
        if (
            doc_from.doctype == defs.Credoctypes.CRE
            and link_to.document.doctype == defs.Credoctypes.CRE
        ):
            cycle = self.introduces_cycle(doc_from=doc_from, link_to=link_to)
            if cycle:
                warn = f"A link between CREs {doc_from.id}-{doc_from.name} and {link_to.document.id}-{link_to.document.name} would introduce cycle {cycle}, skipping"
                logger.warning(warn)
                raise CycleDetectedError(warn)

        self.__graph = self.__add_graph_edge(
            doc_from=doc_from, link_to=link_to, graph=self.__graph
        )

    def __add_graph_edge(
        self,
        doc_from: defs.Document,
        link_to: defs.Link,
        graph: nx.DiGraph,
    ) -> nx.digraph:
        """
        Adds a directed edge to the graph provided
        called by both graph population and speculative cycle finding methods
        hence why it accepts a graph and returns a graph
        """
        if doc_from.name == link_to.document.name:
            raise ValueError(
                f"cannot add an edge from a document to itself, from: {doc_from}, to: {link_to.document}"
            )
        to_doctype = defs.Credoctypes.CRE.value
        if link_to.document.doctype != defs.Credoctypes.CRE.value:
            to_doctype = "Node"

        if doc_from.doctype == defs.Credoctypes.CRE:
            if link_to.ltype == defs.LinkTypes.Contains:
                graph.add_edge(
                    f"{doc_from.doctype.value}: {doc_from.id}",
                    f"{to_doctype}: {link_to.document.id}",
                    ltype=link_to.ltype.value,
                )
            elif link_to.ltype == defs.LinkTypes.PartOf:
                graph.add_edge(
                    f"{to_doctype}: {link_to.document.id}",
                    f"{doc_from.doctype.value}: {doc_from.id}",
                    ltype=defs.LinkTypes.Contains.value,
                )
            elif link_to.ltype == defs.LinkTypes.Related:
                # do nothing if the opposite already exists in the graph, otherwise we introduce a cycle
                if graph.has_edge(
                    f"{to_doctype}: {link_to.document.id}",
                    f"{doc_from.doctype.value}: {doc_from.id}",
                ):
                    return graph

                graph.add_edge(
                    f"{doc_from.doctype.value}: {doc_from.id}",
                    f"{to_doctype}: {link_to.document.id}",
                    ltype=defs.LinkTypes.Related.value,
                )
            elif (
                link_to.ltype == defs.LinkTypes.LinkedTo
                or link_to.ltype == defs.LinkTypes.AutomaticallyLinkedTo
            ):
                graph.add_edge(
                    f"{doc_from.doctype.value}: {doc_from.id}",
                    f"{to_doctype}: {link_to.document.id}",
                    ltype=link_to.ltype.value,
                )
            else:
                raise ValueError(f"link type {link_to.ltype.value} not recognized")
        else:
            graph.add_edge(
                f"{doc_from.doctype.value}: {doc_from.id}",
                f"{to_doctype}: {link_to.document.id}",
                ltype=link_to.ltype.value,
            )
        return graph

    def __load_cre_graph(self, documents: List[defs.Document]):
        for doc in documents:
            if not doc:
                continue
            if doc.doctype == defs.Credoctypes.CRE:
                self.add_cre(cre=doc)
            else:
                self.add_dbnode(dbnode=doc)
            for link in doc.links:
                if not link.document:
                    logger.error(f"doc {doc}, has a link with a document that's None")
                if link.document.doctype == defs.Credoctypes.CRE:
                    self.add_cre(cre=link.document)
                else:
                    self.add_dbnode(dbnode=link.document)
                try:
                    self.add_link(doc_from=doc, link_to=link)
                except CycleDetectedError as cde:
                    pass
