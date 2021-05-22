import './documentNode.scss';

import React, { FunctionComponent, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { DOCUMENT_TYPE_NAMES } from '../../const';
import { CRE, STANDARD } from '../../routes';
import { Document } from '../../types';
import { getDocumentDisplayName, getLinksByType } from '../../utils';

interface DocumentNode {
  node: Document;
}

export const DocumentNode: FunctionComponent<DocumentNode> = ({ node }) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const isStandard = node.doctype === 'Standard';

  if (!node.links || node.links.length === 0) {
    const route = isStandard ? STANDARD : CRE;
    const id = isStandard ? node.name : node.id;
    const hasExternalLink = Boolean(node.hyperlink);

    const linkContent = (
      <>
        <i aria-hidden="true" className="circle icon"></i>
        {getDocumentDisplayName(node)}
        <i aria-hidden="true" className={`${hasExternalLink ? 'external' : 'external square'} icon`}></i>
      </>
    );
    return (
      <>
        <div className={`title external-link document-node`}>
          {hasExternalLink ? (
            <a target="_blank" href={node.hyperlink}>
              {linkContent}
            </a>
          ) : (
            <Link to={`${route}/${id}`}>{linkContent}</Link>
          )}
        </div>
        <div className={`content`}></div>
      </>
    );
  }

  const linksByType = useMemo(() => getLinksByType(node), [node]);
  const active = expanded ? ' active' : '';

  return (
    <>
      <div className={`title${active} document-node`} onClick={() => setExpanded(!expanded)}>
        <i aria-hidden="true" className="dropdown icon"></i>
        {getDocumentDisplayName(node)}
      </div>
      <div className={`content${active} document-node`}>
        {expanded &&
          Object.entries(linksByType).map(([type, links]) => {
            return (
              <div className="document-node__link-type-container" key={type}>
                <div>
                  {node.name} - {node.section} is <b>{DOCUMENT_TYPE_NAMES[type]}</b>:
                </div>
                <div>
                  <div className="accordion ui fluid styled">
                    {links.map((link, i) => (
                      <DocumentNode node={link.document} key={i} />
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
};
