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
    let index = text.toLowerCase().indexOf(term);
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
    doc?.displayName?.toLowerCase().includes(term) || doc?.name?.toLowerCase().includes(term);

  const recursiveFilter = (doc: TreeDocument, term: string) => {
    if (doc.links) {
      const filteredLinks: LinkedTreeDocument[] = [];
      doc.links.forEach((x) => {
        const filteredDoc = recursiveFilter(x.document, term);
        if (filterFunc(x.document, term) || filteredDoc) {
          filteredLinks.push({ ltype: x.ltype, document: filteredDoc || x.document });
        }
      });
      doc.links = filteredLinks;
    }

    if (filterFunc(doc, term) || doc.links?.length) {
      return doc; // Return the document if it or any of its children (links or standards) matches the term
    }
    return null; // Return null if the document and its descendants do not match the term
  };

  //accordion
  const [collapsedItems, setCollapsedItems] = useState<string[]>([]);
  const isCollapsed = (id: string) => collapsedItems.includes(id);
  const toggleItem = (id: string) => {
    if (collapsedItems.includes(id)) {
      setCollapsedItems(collapsedItems.filter((itemId) => itemId !== id));
    } else {
      setCollapsedItems([...collapsedItems, id]);
    }
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

    const creCode = item.id;
    const creName = item.displayName.split(' : ').pop();
    return (
      <List.Item key={Math.random()}>
        <List.Content>
          <List.Header>
            {contains.length > 0 && (
              <div
                className={`arrow ${isCollapsed(item.id) ? '' : 'active'}`}
                onClick={() => toggleItem(item.id)}
              >
                <i aria-hidden="true" className="dropdown icon"></i>
              </div>
            )}
            <Link to={item.url}>
              <span className="cre-code">{applyHighlight(creCode, filter)}:</span>
              <span className="cre-name">{applyHighlight(creName, filter)}</span>
            </Link>
          </List.Header>
          {linkedTo.length > 0 && (
            <List.Description>
              <Label.Group size="small" className="tags">
                {[...new Set(linkedTo.map((x: LinkedTreeDocument) => x.document.name))]
                  .sort()
                  .map((x: string) => (
                    <Link key={Math.random()} to={`/node/standard/${x}`}>
                      <Label>{applyHighlight(x, filter)}</Label>
                    </Link>
                  ))}
              </Label.Group>
            </List.Description>
          )}
          {contains.length > 0 && !isCollapsed(item.id) && (
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
      <main id="explorer-content">
        <h1>Open CRE Explorer</h1>
        <p>
          A visual explorer of Open Common Requirement Enumerations (CREs). Originally created by:{' '}
          <a target="_blank" href="https://zeljkoobrenovic.github.io/opencre-explorer/">
            Zeljko Obrenovic
          </a>
          .
        </p>

        <div id="explorer-wrapper">
          <div className="search-field">
            <input id="filter" type="text" placeholder="Search..." onKeyUp={update} />
            <div id="search-summary"></div>
          </div>
          <div id="graphs-menu">
            <h4 className="menu-title">Explore visually:</h4>
            <ul>
              <li>
                <a href="/explorer/force_graph">Dependency Graph</a>
              </li>
              <li>
                <a href="/explorer/circles">Zoomable circles</a>
              </li>
            </ul>
            {/* <a target="_blank" href="visuals/force-graph-3d-contains.html">
              hierarchy only
            </a>
            <a target="_blank" href="visuals/force-graph-3d-related.html">
              related only
            </a>
            <a target="_blank" href="visuals/force-graph-3d-linked.html">
              links to external standards
            </a>*/}
          </div>
        </div>
        <LoadingAndErrorIndicator loading={dataLoading} error={null} />
        <List>
          {filteredTree?.map((item) => {
            return processNode(item);
          })}
        </List>
      </main>
    </>
  );
};
