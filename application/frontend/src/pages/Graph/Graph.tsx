import React from 'react';
import ForceGraph2D from 'react-force-graph-2d';

// import { Document, PROD_DATA } from '../../data';

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface GraphNode {
  id: string;
  group: number;
}

interface GraphLink {
  source: string;
  target: string;
  value: number;
}

// const convertToGraphData = (documents: Document[]): GraphData => {
//   const graphNodes: GraphNode[] = [];
//   const graphLinks: GraphLink[] = [];

//   documents.forEach((document) => {
//     const documentId = `${document.name} ${document.section}`;
//     graphNodes.push({
//       id: documentId,
//       group: 1,
//     });

//     document.links.forEach((linkedDocument) => {
//       const linkedDocumentId = linkedDocument.document.name;
//       graphNodes.push({
//         id: linkedDocumentId,
//         group: 1,
//       });
//       graphLinks.push({
//         source: documentId,
//         target: linkedDocumentId,
//         value: 1,
//       });
//     });
//   });

//   return {
//     nodes: graphNodes,
//     links: graphLinks,
//   };
// };

export const Graph = () => {
  // const data = convertToGraphData(PROD_DATA);
  return (
    <ForceGraph2D
      graphData={{ nodes: [], links: [] }}
      nodeAutoColorBy="group"
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
