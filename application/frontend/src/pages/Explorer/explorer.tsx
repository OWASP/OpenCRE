import './explorer.scss';

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Label, List } from 'semantic-ui-react';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useDataStore } from '../../providers/DataProvider';
import { LinkedTreeDocument, TreeDocument } from '../../types';

export const Explorer = () => {
  const { dataLoading, dataTree } = useDataStore();
  const [filter, setFilter] = useState('');
  const [filteredTree, setFilteredTree] = useState<TreeDocument[]>();
  const applyHighlight = (text, term) => {
    if (!term) return text;
    var index = text.toLowerCase().indexOf(term);
    if (index >= 0) {
      return (
        <>
          {text.substring(0, index)}
          <span className="highlight">{text.substring(index, index + term.length)}</span>
          {text.substring(index + term.length)}
        </>
      );
    }
    return text;
  };

  const filterFunc = (doc: TreeDocument, term: string) =>
    doc.displayName && doc.displayName.toLowerCase().includes(term);
  const recursiveFilter = (doc: TreeDocument, term: string) => {
    if (doc.links) {
      const filteredLinks: LinkedTreeDocument[] = [];
      doc.links.forEach((x) => {
        const docu = recursiveFilter(x.document, term);
        if (docu) {
          filteredLinks.push({ ltype: x.ltype, document: docu });
        }
      });
      doc.links = filteredLinks;
    }
    if (filterFunc(doc, term) || doc.links?.length) {
      return doc;
    }
    return null;
  };

  useEffect(() => {
    if (dataTree.length) {
      const treeCopy = structuredClone(dataTree);
      const filTree: TreeDocument[] = [];
      treeCopy
        .map((x) => recursiveFilter(x, filter))
        .forEach((x) => {
          if (x) {
            filTree.push(x);
          }
        });
      setFilteredTree(filTree);
    }
  }, [filter, dataTree, setFilteredTree]);

  function processNode(item) {
    if (!item) {
      return <></>;
    }
    const contains = item.links.filter((x) => x.ltype === 'Contains');
    const linkedTo = item.links.filter((x) => x.ltype === 'Linked To');
    return (
      <List.Item key={Math.random()}>
        <List.Icon name="folder" />
        <List.Content>
          <List.Header>
            <Link to={item.url}>{applyHighlight(item.displayName, filter)}</Link>
          </List.Header>
          {linkedTo.length > 0 && (
            <List.Description>
              <Label.Group size="tiny" tag>
                {[...new Set(linkedTo.map((x: LinkedTreeDocument) => x.document.name))]
                  .sort()
                  .map((x: string) => (
                    <Link key={Math.random()} to={`/node/standard/${x}`}>
                      <Label>{x}</Label>
                    </Link>
                  ))}
              </Label.Group>
            </List.Description>
          )}
          {contains.length > 0 && (
            <List.List>{contains.map((child) => processNode(child.document))}</List.List>
          )}
        </List.Content>
      </List.Item>
    );
  }
  function update(event) {
    setFilter(event.target.value.toLowerCase());
  }

  return (
    <>
      <div id="explorer-content">
        <h1>
          <b>Explorer</b>
        </h1>
        <p>
          A visual explorer of Open Common Requirement Enumerations (CREs). Originally created by:{' '}
          <a target="_blank" href="https://zeljkoobrenovic.github.io/opencre-explorer/">
            Zeljko Obrenovic
          </a>
          .
        </p>

        <div id="explorer-wrapper">
          <div>
            <input id="filter" type="text" placeholder="search..." onKeyUp={update} />
            <div id="search-summary"></div>
          </div>
          <div id="graphs">
            graphs (3D):
            <a target="_blank" href="force_graph">
              CRE dependencies
            </a>{' '}
            -
            {/* <a target="_blank" href="visuals/force-graph-3d-contains.html">
              hierarchy only
            </a>{' '}
            -
            <a target="_blank" href="visuals/force-graph-3d-related.html">
              related only
            </a>{' '}
            |
            <a target="_blank" href="visuals/force-graph-3d-linked.html">
              links to external standards
            </a>{' '} */}
            |
            <a target="_blank" href="circles">
              zoomable circles
            </a>
          </div>
        </div>
        <LoadingAndErrorIndicator loading={dataLoading} error={null} />
        <List>
          {filteredTree?.map((item) => {
            return processNode(item);
          })}
        </List>
      </div>
    </>
  );
};
