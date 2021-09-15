import React, { useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useQuery } from 'react-query';
import { useEnvironment } from '../../hooks';
import { useParams } from 'react-router-dom';
import { Document, LinkTypes } from '../../types';
import { node } from 'prop-types';

// import { Document, PROD_DATA } from '../../data';

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface GraphNode {
  id: string;
  group: number;
  document: Document;
}

interface GraphLink {
  source: string;
  target: string;
  type: string;
  value: number;
  // sourceDoc:Document,
  // targetDoc:Document,
}


const convertToGraphData = (documents: Document[]): GraphData => {
  const graphNodes: GraphNode[] = [];
  const graphLinks: GraphLink[] = [];
  documents.forEach((document) => {
    var documentId = ""
    if (document.doctype.toLowerCase() == "cre") {
      documentId = `CRE: ${document.id} ${document.name}`;
    }
    if (document.doctype.toLowerCase() == "standard") {
      documentId = `Standard: ${document.name} ${document.section}`
      if (document.subsection) {
        documentId += `  ${document.subsection}`
      }
    }
    graphNodes.push({
      id: documentId,
      group: 1,
      document: document,
    });
    //TODO: annotate connections with linktypes
    var links = document.links ? document.links : []
    links.forEach((linkedDocument) => {
      const ldoc = linkedDocument.document
      var linkedDocumentId = ""
      if (ldoc.doctype.toLowerCase() == "cre") {
        linkedDocumentId = `CRE: ${ldoc.id} ${ldoc.name}`;
      }
      if (ldoc.doctype.toLowerCase() == "standard") {
        linkedDocumentId = `Standard: ${ldoc.name} ${ldoc.section}`
        if (document.subsection) {
          linkedDocumentId += `  ${ldoc.subsection}`
        }
      }
      graphNodes.push({
        id: linkedDocumentId,
        group: LinkTypes[linkedDocument.type],
        document: ldoc,
      });
      graphLinks.push({
        source: documentId,
        target: linkedDocumentId,
        value: 1,
        type: linkedDocument.type,
      });
    });
  });

  return {
    nodes: graphNodes,
    links: graphLinks,
  };
};


const doQuery = (path: string): Document[] => {
  if (!path) { return [] }
  const { apiUrl } = useEnvironment();
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  const { error, data, refetch } = useQuery<{ data: Document[]; total_pages: number }, string>(
    'document',
    () => fetch(`${apiUrl}${path}`).then((res) => res.json()),
    {
      retry: false,
      enabled: false,
      onSettled: () => {
        setLoading(false);
      },
    }
  );

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    refetch();
  }, [page, path]);

  return data ? data.data : [];
}


export const Graph = () => {

  const { id } = useParams();
  const documents = doQuery(`/id/${id}`)
  const gData = convertToGraphData(documents);

  const handleNodeClick = (node) => {
    const { nodes, links } = gData;

    var documents: Document[] = []
    if (node.document.doctype == "CRE") {
      documents = [node.document]
      // documents = doQuery(`/id/${node.document.id}`)
    } else if (node.document.doctype == "Standard") {
      var path = `/standard/${node.document.name}?section=${node.document.section}`
      if (node.document.subsection) {
        path += `&subsection=${node.document.subsection}`
      }
      // documents = doQuery(path)
      documents = [node.document]
    }
    const newData = convertToGraphData(documents)
    console.log(newData)
    var newLinks = links.slice();
    var newNodes = nodes.slice();
    console.log(newNodes.length)

    newData.links.forEach(element => {
      newLinks.push(element)
    });
    newData.nodes.forEach(node=>{
      newNodes.push(node)
    });
    console.log(newNodes.length)

    return ({ nodes: newNodes, links: newLinks });
  }


  return (
    <ForceGraph2D
      graphData={gData}
      nodeAutoColorBy="group"
      onNodeClick={handleNodeClick}
      linkAutoColorBy="group"
      linkDirectionalArrowLength={3.5}
      linkDirectionalArrowRelPos={1}
      nodeCanvasObject={(node, ctx, globalScale) => {
        const label = node.id;
        const fontSize = 12 / globalScale;
        ctx.font = `${fontSize}px Sans-Serif`;
        const textWidth = ctx.measureText(label as string).width;
        const backgroundDimensions = [textWidth, fontSize].map((n) => n + fontSize);

        ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
        ctx.fillRect(
          (node.x || 0) - backgroundDimensions[0] / 2,
          (node.y || 0) - backgroundDimensions[1] / 2,
          backgroundDimensions[0],
          backgroundDimensions[1]
        );

        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        // @ts-ignore
        ctx.fillStyle = node.color;
        ctx.fillText(label as string, node.x || 0, node.y || 0);
        // @ts-ignore
        node.__bckgDimensions = backgroundDimensions; // to re-use in nodePointerAreaPaint
      }}
      nodePointerAreaPaint={(node, color, ctx) => {
        ctx.fillStyle = color;
        // @ts-ignore
        const backgroundDimensions = node.__bckgDimensions;
        backgroundDimensions &&
          ctx.fillRect(
            (node.x || 0) - backgroundDimensions[0] / 2,
            (node.y || 0) - backgroundDimensions[1] / 2,
            backgroundDimensions[0],
            backgroundDimensions[1]
          );
      }}
    />
  );
};
