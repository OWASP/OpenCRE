// import React from 'react';
// import ForceGraph2D from 'react-force-graph-2d';

// import { Document, PROD_DATA } from '../../data';

// interface GraphData {
//   nodes: GraphNode[];
//   links: GraphLink[];
// }

// interface GraphNode {
//   id: string;
//   group: number;
// }

// interface GraphLink {
//   source: string;
//   target: string;
//   value: number;
// }

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

// export const Graph = () => {
//   // const data = convertToGraphData(PROD_DATA);
//   return (
//     <ForceGraph2D
//       graphData={{ nodes: [], links: [] }}
//       nodeAutoColorBy="group"
//       nodeCanvasObject={(node, ctx, globalScale) => { 
//         const label = node.id;
//         const fontSize = 12 / globalScale;
//         ctx.font = `${fontSize}px Sans-Serif`;
//         const textWidth = ctx.measureText(label as string).width;
//         const backgroundDimensions = [textWidth, fontSize].map((n) => n + fontSize);

//         ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
//         ctx.fillRect(
//           (node.x || 0) - backgroundDimensions[0] / 2,
//           (node.y || 0) - backgroundDimensions[1] / 2,
//           backgroundDimensions[0],
//           backgroundDimensions[1]
//         );

//         ctx.textAlign = 'center';
//         ctx.textBaseline = 'middle';
//         // @ts-ignore
//         ctx.fillStyle = node.color;
//         ctx.fillText(label as string, node.x || 0, node.y || 0);

//         // @ts-ignore
//         node.__bckgDimensions = backgroundDimensions; // to re-use in nodePointerAreaPaint
//       }}
//       nodePointerAreaPaint={(node, color, ctx) => {
//         ctx.fillStyle = color;
//         // @ts-ignore
//         const backgroundDimensions = node.__bckgDimensions;
//         backgroundDimensions &&
//           ctx.fillRect(
//             (node.x || 0) - backgroundDimensions[0] / 2,
//             (node.y || 0) - backgroundDimensions[1] / 2,
//             backgroundDimensions[0],
//             backgroundDimensions[1]
//           );
//       }}
//     />
//   );
// };

import React, {useEffect, useState } from 'react';

import ReactFlow, {
  removeElements,
  addEdge,
  MiniMap,
  Controls,
  Background,
  FlowElement,
} from 'react-flow-renderer';
import { Document, LinkedDocument } from '../../types';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';
import { useEnvironment } from '../../hooks';


const initialElements = [
  {
    id: '1',
    type: 'input', // input node
    data: { label: 'Input Node' },
    position: { x: 250, y: 25 },
  },
  // default node
  {
    id: '2',
    // you can also pass a React component as a label
    data: { label: <div>Default Node</div> },
    position: { x: 100, y: 125 },
  },
  {
    id: '3',
    type: 'output', // output node
    data: { label: 'Output Node' },
    position: { x: 250, y: 250 },
  },
  // animated edge
  { id: 'e1-2', source: '1', target: '2', animated: true },
  { id: 'e2-3', source: '2', target: '3' },
];

const DocumentToReactFlowNode = (cDoc:Document) => {
  if (!cDoc){
    return {}
  }
  var root:any = [{
    id: cDoc.id,
    type: cDoc.doctype,
    data:{label: <a href={cDoc.hyperlink}> document.name</a>}, // TODO: add section/subsection
  }]
  if (cDoc.links){
  for (var link of cDoc.links){
      root.concat([{
          id: link.document.id,
          type: link.document.doctype,
          data: {label: <a href={link.document.hyperlink}> document.name</a>}, // TODO: add section/subsection
          }]);
      root.concat([{
          id: cDoc.id +'-'+link.document.id,
          target: link.document.id,
          source: cDoc.id,
          label: link.ltype,
          animated:true,
        }])
  }}
  return root;
};

const onLoad = (reactFlowInstance) => {
  console.log('flow loaded:', reactFlowInstance);
  reactFlowInstance.fitView();
};

export const Graph = () => {
  const { id } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);

  console.log('flow runnin:',id);

  const { error, data, refetch } = useQuery<{ data: Document; }, string>(
    'cre',
    () => fetch(`${apiUrl}/id/${id}`).then((res) => res.json()),
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
  }, [id]);

  console.log(data)
  const cre = data?.data;
  const [elements, setElements] = useState(cre?DocumentToReactFlowNode(cre):"");
  const onConnect = (params) => setElements((els) => addEdge(params, els));
    
  return (
    <ReactFlow
    elements={elements}
    onConnect={onConnect}
    onLoad={onLoad}
    snapToGrid={true}
    snapGrid={[15, 15]}
    >
      <MiniMap
        nodeStrokeColor='#0041d0'
        nodeColor='#00FF00'
        nodeBorderRadius={2}
      />
      <Controls />
      <Background color="#ffff" gap={16} />
    </ReactFlow>
  );
};
