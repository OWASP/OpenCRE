import sys
import networkx as nx
from typing import List, Tuple
from application.defs import cre_defs as defs


class CRE_Graph:
    graph: nx.Graph = None
    __parent_child_subgraph = None
    __instance: "CRE_Graph" = None

    @classmethod
    def instance(cls, documents: List[defs.Document] = None) -> "CRE_Graph":
        if cls.__instance is None:
            cls.__instance = cls.__new__(cls)
            cls.graph = nx.DiGraph()
            cls.graph = cls.__load_cre_graph(documents=documents)
        return cls.__instance

    def __init__(sel):
        raise ValueError("CRE_Graph is a singleton, please call instance() instead")

    def add_node(self, *args, **kwargs):
        return self.graph.add_node(*args, **kwargs)

    def introduces_cycle(self, doc_from: defs.Document, link_to: defs.Link):
        try:
            existing_cycle = nx.find_cycle(self.graph)
            if existing_cycle:
                raise ValueError(
                    "Existing graph contains cycle,"
                    "this not a recoverable error,"
                    f" manual database actions are required {existing_cycle}"
                )
        except nx.exception.NetworkXNoCycle:
            pass  # happy path, we don't want cycles
        new_graph = self.graph.copy()

        # this needs our special add_edge but with the copied graph
        new_graph = self.add_graph_edge(
            doc_from=doc_from, link_to=link_to, graph=new_graph
        )
        try:
            return nx.find_cycle(new_graph)
        except nx.NetworkXNoCycle:
            return False

    def get_hierarchy(self, rootIDs: List[str], creID: str):
        if creID in rootIDs:
            return 0

        if self.__parent_child_subgraph == None:
            if len(self.graph.edges) == 0:
                raise ValueError("Graph has no edges")
            include_cres = []
            for el in self.graph.edges:
                edge_data = self.graph.get_edge_data(*el)
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
            self.__parent_child_subgraph = self.graph.subgraph(set(include_cres))

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
            except (
                nx.NodeNotFound
            ) as nnf:  # If the CRE is not in the parent/children graph it means that it's a lone CRE, so it's a root and we return 0
                return 0
            except (
                nx.NetworkXNoPath
            ) as nxnp:  # If there is no path to the CRE, continue
                continue
        return shortest_path

    def get_path(self, start: str, end: str) -> List[Tuple[str, str]]:
        try:
            return nx.shortest_path(self.graph, start, end)
        except nx.NetworkXNoPath:
            return []

    @classmethod
    def add_cre(cls, dbcre: defs.CRE, graph: nx.DiGraph) -> nx.DiGraph:
        if dbcre:
            cls.graph.add_node(f"CRE: {dbcre.id}", internal_id=dbcre.id)
        else:
            logger.error("Called with dbcre being none")
        return graph

    @classmethod
    def add_dbnode(cls, dbnode: defs.Node, graph: nx.DiGraph) -> nx.DiGraph:
        if dbnode:
            cls.graph.add_node(
                "Node: " + str(dbnode.id),
                internal_id=dbnode.id,
            )
        else:
            logger.error("Called with dbnode being none")
        return graph

    @classmethod
    def add_graph_edge(
        cls,
        doc_from: defs.Document,
        link_to: defs.Link,
        graph: nx.DiGraph,
    ) -> nx.digraph:

        to_doctype = defs.Credoctypes.CRE.value
        if link_to.document.doctype != defs.Credoctypes.CRE.value:
            to_doctype = "Node"

        if doc_from.doctype == defs.Credoctypes.CRE:
            if link_to.ltype == defs.LinkTypes.Contains:
                graph.add_edge(
                    f"{doc_from.doctype}: {doc_from.id}",
                    f"{to_doctype}: {link_to.document.id}",
                    ltype=link_to.ltype,
                )
            elif link_to.ltype == defs.LinkTypes.PartOf:
                graph.add_edge(
                    f"{to_doctype}: {link_to.document.id}",
                    f"{doc_from.doctype}: {doc_from.id}",
                    ltype=defs.LinkTypes.Contains,
                )
            elif link_to.ltype == defs.LinkTypes.Related:
                # do nothing if the opposite already exists in the graph, otherwise we introduce a cycle
                if graph.has_edge(
                    f"{to_doctype}: {link_to.document.id}",
                    f"{doc_from.doctype}: {doc_from.id}",
                ):
                    return graph

                graph.add_edge(
                    f"{doc_from.doctype}: {doc_from.id}",
                    f"{to_doctype}: {link_to.document.id}",
                    ltype=defs.LinkTypes.Related,
                )
        else:
            graph.add_edge(
                f"{doc_from.doctype}: {doc_from.id}",
                f"{to_doctype}: {link_to.document.id}",
                ltype=link_to.ltype,
            )
        return graph

    @classmethod
    def __load_cre_graph(cls, documents: List[defs.Document]) -> nx.Graph:
        graph = cls.graph
        if not graph:
            graph = nx.DiGraph()

        for doc in documents:
            from_doctype = None
            if doc.doctype == defs.Credoctypes.CRE:
                graph = cls.add_cre(dbcre=doc, graph=graph)
                from_doctype = defs.Credoctypes.CRE
            else:
                graph = cls.add_dbnode(dbnode=doc, graph=graph)
                from_doctype = doc.doctype
            for link in doc.links:
                if link.document.doctype == defs.Credoctypes.CRE:
                    graph = cls.add_cre(dbcre=link.document, graph=graph)
                else:
                    graph = cls.add_dbnode(dbnode=link.document, graph=graph)
            graph = cls.add_graph_edge(doc_from=doc, link_to=link, graph=graph)
        cls.graph = graph
        return graph
