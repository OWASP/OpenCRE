import Elk, { ElkEdge, ElkNode, ElkPort, ElkPrimitiveEdge } from 'elkjs';
import React, { useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Elements,
  FlowElement,
  MiniMap,
  Node,
  ReactFlowProps,
  addEdge,
  isEdge,
  isNode,
  removeElements,
} from 'react-flow-renderer';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';
import { FlowNode } from 'typescript';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { DOCUMENT_TYPES } from '../../const';
import { useEnvironment } from '../../hooks';
import { Document, LinkedDocument } from '../../types';

interface ReactFlowNode {}
interface CREGraph {
  nodes: Node<ReactFlowNode>[];
  edges: Edge<ReactFlowNode>[];
  root: (Node<ReactFlowNode> | Edge<ReactFlowNode>)[];
}

const documentToReactFlowNode = (cDoc: Document | any): CREGraph => {
  let result: CREGraph = { nodes: [], edges: [], root: [] };
  let root: (Node<ReactFlowNode> | Edge<ReactFlowNode>)[] = [];
  let node = {
    id: cDoc.id,
    type: cDoc.doctype,
    position: { x: 0, y: 0 },
    data: {
      label: (
        <a target="_blank" href={cDoc.hyperlink}>
          {' '}
          {cDoc.id} - {cDoc.name}
        </a>
      ),
    },
  };
  root.push(node);
  result.nodes.push(node);

  if (cDoc.links) {
    for (let link of cDoc.links) {
      const { id, doctype, hyperlink, name, section, subsection, ruleID } = link.document;
      const unique_node_id = id || section || name;
      const node_label = name + ' - ' + doctype === DOCUMENT_TYPES.TYPE_TOOL ? ruleID : section || id;
      let node = {
        id: unique_node_id,
        type: doctype,
        position: { x: 0, y: 0 },
        data: {
          label: (
            <a target="_blank" href={hyperlink}>
              {' '}
              {node_label}
            </a>
          ),
        }, // TODO: add section/subsection
      };
      let edge = {
        type: link.ltype,
        data: { label: <></> },
        id: cDoc.id + '-' + unique_node_id,
        source: cDoc.id,
        target: unique_node_id,
        label: link.ltype,
        animated: true,
      };
      result.root.push(node);
      result.nodes.push(node);

      result.edges.push(edge);
      result.root.push(edge);
    }
  }
  return result;
};

const onLoad = (reactFlowInstance) => {
  reactFlowInstance.fitView();
};

export const Graph = () => {
  const { id } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(true);

  const { error, data, refetch } = useQuery<{ data: Document }, string>(
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

  const [layout, setLayout] = useState<(Node<ReactFlowNode> | Edge<ReactFlowNode>)[]>();

  useEffect(() => {
    async function draw() {
      if (data) {
        console.log('flow running:', id);

        let cre = data.data;
        let graph = documentToReactFlowNode(cre);
        const els = await createGraphLayoutElk(graph.nodes, graph.edges);
        setLayout(els);
      }
    }
    draw();
  }, [data]);

  return loading || error ? (
    <LoadingAndErrorIndicator loading={loading} error={error} />
  ) : layout ? (
    <ReactFlow
      elements={layout}
      // onConnect={onConnect}
      onLoad={onLoad}
      snapToGrid={true}
      snapGrid={[15, 15]}
    >
      <MiniMap nodeStrokeColor="#0041d0" nodeColor="#00FF00" nodeBorderRadius={2} />
      <Controls />
      <Background color="#ffff" gap={16} />
    </ReactFlow>
  ) : (
    <div />
  );
};

const createGraphLayoutElk = async (
  flowNodes: Node<ReactFlowNode>[],
  flowEdges: Edge<ReactFlowNode>[]
): Promise<(Node<ReactFlowNode> | Edge<ReactFlowNode>)[]> => {
  const elkNodes: ElkNode[] = [];
  const elkEdges: ElkPrimitiveEdge[] = [];

  flowNodes.forEach((node) => {
    let ports: ElkPort[] = [];
    ports = [
      {
        id: `${node.id}`,
        layoutOptions: {
          'org.eclipse.elk.port.side': 'EAST',
          'org.eclipse.elk.port.index': '10',
        },
      },
      // {
    ];

    elkNodes.push({
      id: `${node.id}`,
      width: 200,
      height: 50,
      ports,
      // layoutOptions: { 'org.eclipse.elk.portConstraints': 'FIXED_SIDE' },
    });
  });

  flowEdges.forEach((edge) => {
    let sourcePort;

    if (edge.source) {
      // Create a link with the node port on branch node type
      // sourcePort = `${edge.source}`
      let edg = {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        // sourcePort,
      };
      console.log(edg);
      elkEdges.push(edg);
    } else {
      console.log('edge does not have a source?');
      console.log(edge);
    }
  });
  let elk = new Elk();
  console.log(elkEdges);
  console.log(elkNodes);
  console.log(flowNodes);
  const newGraph = await elk.layout({
    id: 'root',
    layoutOptions: {
      'spacing.nodeNodeBetweenLayers': '100',
      // 'elk.direction': 'DOWN',

      'org.eclipse.elk.algorithm': 'org.eclipse.elk.radial', //'org.eclipse.elk.layered',
      'org.eclipse.elk.aspectRatio': '1.0f',
      'org.eclipse.elk.force.repulsion': '1.0',
      'org.eclipse.elk.spacing.nodeNode': '100',
      'org.eclipse.elk.padding': '10',
      'elk.spacing.edgeNode': '30',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.partitioning.activate': 'true',
      nodeFlexibility: 'NODE_SIZE',
      'org.eclipse.elk.layered.allowNonFlowPortsToSwitchSides': 'true',
    },
    children: elkNodes,
    edges: elkEdges,
  });

  return [
    ...flowNodes.map((nodeState) => {
      const node = newGraph?.children?.find((n) => n.id === nodeState.id);

      if (node?.x && node?.y && node?.width && node?.height) {
        nodeState.position = {
          x: node.x + Math.random() / 1000, // unfortunately we need this little hack to pass a slightly different position so react-flow react to the changes
          y: node.y,
        };
        // if (nodeState?.data?.elementType !== 'Hidden') {
        //   nodeState.style = {}
        // }
      }
      nodeState.style = { border: '1px solid', padding: '0.5%', margin: '0.5%' };
      return nodeState;
    }),
    ...flowEdges.map((e) => {
      e.style = {};
      return e;
    }),
  ];
};
