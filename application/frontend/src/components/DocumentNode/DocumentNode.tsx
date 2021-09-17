import './documentNode.scss';

import React, { FunctionComponent, useMemo, useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

import { DOCUMENT_TYPE_NAMES, TYPE_IS_PART_OF } from '../../const';
import { CRE, STANDARD } from '../../routes';
import { Document } from '../../types';
import { getDocumentDisplayName, getLinksByType } from '../../utils';
import { useEnvironment } from '../../hooks';
import axios from 'axios';
import { LoadingAndErrorIndicator } from '../LoadingAndErrorIndicator';

interface DocumentNode {
  node: Document,
  linkType: string;
}

const nestedDocumentLinkTypes = [TYPE_IS_PART_OF]

export const DocumentNode: FunctionComponent<DocumentNode> = ({ node, linkType }) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const isStandard = node.doctype === 'Standard';
  const { apiUrl } = useEnvironment();
  const [nestedNode, setNestedNode] = useState<Document>();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const id = isStandard ? node.name : node.id;

  var usedNode = nestedNode || node;
  const linksByType = useMemo(() => getLinksByType(usedNode), [usedNode]);

  useEffect( () => {
    if ( !isStandard && nestedDocumentLinkTypes.includes(linkType) ) {
      axios.get(`${apiUrl}/id/${id}`)
      .then(function (response) {
        setNestedNode(response.data.data);
        setExpanded(true);
        setError('');
      })
      .catch(function (axiosError) {
        setError(axiosError);
      });
    }
  }, [id]);

  if ( ( !usedNode.links || usedNode.links.length === 0)) {
    const route = isStandard ? STANDARD : CRE;
    const hasExternalLink = Boolean(usedNode.hyperlink);
    var hyperlink = usedNode.hyperlink ? usedNode.hyperlink : ""
    const linkContent = (
      <>
        <i aria-hidden="true" className="circle icon"></i>
        {getDocumentDisplayName(usedNode)}
        <i aria-hidden="true" className={`${hasExternalLink ? 'external' : 'external square'} icon`}></i>
      </>
    );
    return (
      <>

        {hasExternalLink ? (
          <p className={`title external-link document-node external square f1`}>
            <a target="_blank" href={hyperlink}>
              {linkContent}
            </a></p>
        ) : <div className={`title external-link document-node f2`}>
            <Link to={`${route}/${id}`}>{linkContent}</Link></div>
        }
        <div className={`content`}></div>
      </>
    );
  }

  
  const active = expanded ? ' active' : '';

  return (
    <>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      <div className={`title${active} document-node`} onClick={() => setExpanded(!expanded)}>
        <i aria-hidden="true" className="dropdown icon"></i>
        <a href={usedNode.hyperlink}>
          {getDocumentDisplayName(usedNode)}
        </a>
      </div>
      <div className={`content${active} document-node`}>
        {expanded &&
          Object.entries(linksByType).map(([type, links]) => {
            return (
              <div className="document-node__link-type-container" key={type}>
                <div>
                  { usedNode.hyperlink
                    ? <a href={usedNode.hyperlink}> {usedNode.name} - {usedNode.section} </a>
                    : <span > {usedNode.name} - {usedNode.section} </span>
                  }
                  <b> {DOCUMENT_TYPE_NAMES[type]}</b>:
                </div>
                <div>
                  <div className="accordion ui fluid styled f0">
                    { links.map( (link, i) => 
                        <DocumentNode node={link.document} linkType={type} key={i} />
                      )
                    }
                  </div>
                </div>
              </div>
            );
          })}
      </div>
    </>
  );
};
