import React, { useEffect, useRef, useState } from 'react';
// @ts-ignore
import ForceGraph2D from 'react-force-graph-2d';
import { useEnvironment } from '../../hooks';
import axios from 'axios';
import { Loader, Message } from 'semantic-ui-react';

export const ChangesetGraph = ({ runId }: { runId: string }) => {
  const env = useEnvironment();
  const [graphData, setGraphData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fgRef = useRef<any>();

  useEffect(() => {
    const fetchGraphData = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axios.get(`${env.apiUrl}/../admin/imports/runs/${runId}/changeset/graph`);
        
        // Ensure nodes have numeric id or we use the string id directly.
        // ForceGraph2D expects `id` on nodes and `source`/`target` on links matching those ids.
        setGraphData(response.data);
      } catch (err: any) {
        console.error(err);
        setError('Failed to load graph data.');
      }
      setLoading(false);
    };

    fetchGraphData();
  }, [runId, env.apiUrl]);

  useEffect(() => {
    if (graphData && fgRef.current) {
      // Small delay to ensure the graph is rendered before adjusting forces
      setTimeout(() => {
        fgRef.current.d3Force('charge').strength(-150);
        fgRef.current.zoom(1.5, 400);
      }, 500);
    }
  }, [graphData]);

  if (loading) return <Loader active inline="centered" />;
  if (error) return <Message negative>{error}</Message>;

  if (!graphData || !graphData.nodes || graphData.nodes.length === 0) {
    return <Message info>No graphical changes to display.</Message>;
  }

  // Check if graph is too large to render nicely (e.g. > 1000 nodes)
  if (graphData.nodes.length > 1000) {
    return <Message warning>Graph is too large to render ({graphData.nodes.length} nodes). Please use the textual summary.</Message>;
  }

  return (
    <div style={{ height: '500px', border: '1px solid #ddd', borderRadius: '4px', marginTop: '1rem', overflow: 'hidden' }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={{ nodes: graphData.nodes, links: graphData.edges }}
        nodeLabel="label"
        nodeColor={(node: any) => {
          if (node.status === 'added') return '#21ba45'; // green
          if (node.status === 'deleted') return '#db2828'; // red
          if (node.status === 'updated') return '#fbbd08'; // orange
          return node.type === 'CRE' ? '#2185d0' : '#767676'; // blue for CRE, grey for unchanged standard
        }}
        linkColor={(link: any) => {
          if (link.status === 'added') return '#21ba45';
          if (link.status === 'deleted') return '#db2828';
          return '#cccccc';
        }}
        nodeRelSize={6}
        linkWidth={(link: any) => (link.status === 'unchanged' ? 1 : 2)}
      />
    </div>
  );
};
