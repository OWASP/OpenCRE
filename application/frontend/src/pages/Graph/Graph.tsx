import React, { useEffect, useState } from 'react';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';

import ReactFlow, {
  removeElements,
  addEdge,
  MiniMap,
  Controls,
  Background,
  FlowElement,
  Node,
  Edge,
  ReactFlowProps,
  isNode,
  isEdge,
} from 'react-flow-renderer';

import { Document, LinkedDocument } from '../../types';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';
import { useEnvironment } from '../../hooks';
import Elk from "elkjs";
import { ElementHandle } from 'puppeteer';


interface ReactFlowNode { }

//  TODO: I'm missing layouting, you can add layout to react flow with elkjs https://github.com/kieler/elkjs

const documentToReactFlowNode = (cDoc: (Document | any)): FlowElement[] => {
  let ypos = 0
  let xpos = 0
  const maxXpos = 10000
  const maxYpos = 10000
  let root: (Node<ReactFlowNode> | Edge<ReactFlowNode>)[] = [{
    id: cDoc.id,
    type: cDoc.doctype,
    position: { x: xpos, y: ypos },
    data: { label: <a href={cDoc.hyperlink}> document.name</a> }, // TODO: add section/subsection
  }]

  if (cDoc.links) {
    for (let link of cDoc.links) {
      const { id, doctype, hyperlink, name, section, subsection } = link.document
      const unique_node_id = id || section
      if (xpos < maxYpos) {
        xpos += 200
        // xpos +=
      } else {
        xpos = 0
        ypos += 200
      }
      // if (xpos >= maxXpos) { xpos = 0 }
      root.push({
        id: unique_node_id,
        type: doctype,
        position: { x: xpos, y: ypos },
        data: { label: <a href={hyperlink}> {name}</a> }, // TODO: add section/subsection
      });

      root.push({
        type: link.ltype,
        data: { label: <></> },
        id: cDoc.id + '-' + unique_node_id,
        source: cDoc.id,
        target: unique_node_id,
        label: link.ltype,
        animated: true,
      })
    }
  }
  console.log(root)
  return root;
};

const onLoad = (reactFlowInstance) => {
  console.log('flow loaded:', reactFlowInstance);
  reactFlowInstance.fitView();
};

export const Graph = () => {

  const [elements, setElements] = useState([]);

  const { id } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(true);

  console.log('flow runnin:', id);

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

  let cre = data?.data

  return (
    loading || error ?
      <LoadingAndErrorIndicator loading={loading} error={error} />
      :
      <ReactFlow
        elements={documentToReactFlowNode(cre)}
        // onConnect={onConnect}
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
    // }
  );
};
