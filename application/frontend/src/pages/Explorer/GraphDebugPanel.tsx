import './GraphDebugPanel.scss';

import React from 'react';
import { Icon, Label, List, Table } from 'semantic-ui-react';

import { TreeDocument } from '../../types';

interface NodeStats {
  id: string;
  displayName: string;
  doctype: string;
  inDegree: number;
  outDegree: number;
  isRoot: boolean;
  linkTypes: Record<string, number>;
}

interface GraphDebugPanelProps {
  dataStore: Record<string, TreeDocument>;
}

const computeStats = (dataStore: Record<string, TreeDocument>): NodeStats[] => {
  const inDegreeMap: Record<string, number> = {};
  const linkTypeMap: Record<string, Record<string, number>> = {};

  Object.values(dataStore).forEach((doc) => {
    if (!inDegreeMap[doc.id]) inDegreeMap[doc.id] = 0;
    if (!linkTypeMap[doc.id]) linkTypeMap[doc.id] = {};

    if (doc.links) {
      doc.links.forEach((link) => {
        if (!link.document) return;
        const targetId = link.document.id;
        if (!inDegreeMap[targetId]) inDegreeMap[targetId] = 0;
        if (link.ltype === 'Contains') {
          inDegreeMap[targetId] = (inDegreeMap[targetId] || 0) + 1;
        }
        linkTypeMap[doc.id][link.ltype] = (linkTypeMap[doc.id][link.ltype] || 0) + 1;
      });
    }
  });

  return Object.values(dataStore)
    .filter((doc) => doc.doctype === 'CRE')
    .map((doc) => ({
      id: doc.id,
      displayName: doc.displayName,
      doctype: doc.doctype,
      inDegree: inDegreeMap[doc.id] || 0,
      outDegree: doc.links ? doc.links.length : 0,
      isRoot: (inDegreeMap[doc.id] || 0) === 0,
      linkTypes: linkTypeMap[doc.id] || {},
    }))
    .sort((a, b) => (b.isRoot ? 1 : 0) - (a.isRoot ? 1 : 0));
};

export const GraphDebugPanel = ({ dataStore }: GraphDebugPanelProps) => {
  const stats = computeStats(dataStore);
  const rootCount = stats.filter((s) => s.isRoot).length;
  const totalNodes = stats.length;

  return (
    <div className="graph-debug-panel">
      <div className="graph-debug-panel__header">
        <Icon name="bug" />
        <strong>Graph Debug Info</strong>
        <span className="graph-debug-panel__summary">
          {totalNodes} CRE nodes — {rootCount} roots
        </span>
      </div>

      <div className="graph-debug-panel__legend">
        <Label size="tiny" color="green">
          Root
        </Label>
        <span> = no incoming Contains links</span>
      </div>

      <div className="graph-debug-panel__table-wrap">
        <Table compact size="small" celled>
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>Node</Table.HeaderCell>
              <Table.HeaderCell>Root?</Table.HeaderCell>
              <Table.HeaderCell>In</Table.HeaderCell>
              <Table.HeaderCell>Out</Table.HeaderCell>
              <Table.HeaderCell>Link Types</Table.HeaderCell>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {stats.map((s) => (
              <Table.Row key={s.id} positive={s.isRoot}>
                <Table.Cell>
                  <span className="graph-debug-panel__node-name" title={s.displayName}>
                    {s.id}
                  </span>
                </Table.Cell>
                <Table.Cell textAlign="center">
                  {s.isRoot && (
                    <Label size="tiny" color="green">
                      Root
                    </Label>
                  )}
                </Table.Cell>
                <Table.Cell textAlign="center">{s.inDegree}</Table.Cell>
                <Table.Cell textAlign="center">{s.outDegree}</Table.Cell>
                <Table.Cell>
                  <List horizontal size="mini">
                    {Object.entries(s.linkTypes).map(([ltype, count]) => (
                      <List.Item key={ltype}>
                        <Label size="mini">
                          {ltype}
                          <Label.Detail>{count}</Label.Detail>
                        </Label>
                      </List.Item>
                    ))}
                  </List>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
      </div>
    </div>
  );
};
