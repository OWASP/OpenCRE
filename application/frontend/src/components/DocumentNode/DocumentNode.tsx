import './documentNode.scss';

import React, { FunctionComponent, useMemo, useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

import { DOCUMENT_TYPE_NAMES, TYPE_IS_PART_OF, TYPE_CONTAINS, TYPE_LINKED_TO } from '../../const';
import { Document } from '../../types';
import { getDocumentDisplayName, groupLinksByType } from '../../utils';
import { useEnvironment } from '../../hooks';
import axios from 'axios';
import { LoadingAndErrorIndicator } from '../LoadingAndErrorIndicator';
import { getApiEndpoint, getInternalUrl } from '../../utils/document';

interface DocumentNode {
  node: Document,
  linkType: string;
}

const linkTypesToNest = [TYPE_IS_PART_OF]
const linkTypesExcludedInNesting = [TYPE_CONTAINS]

export const DocumentNode: FunctionComponent<DocumentNode> = ({ node, linkType }) => {
  const [expanded, setExpanded] = useState<boolean>(false);
  const isStandard = node.doctype === 'Standard';
  const { apiUrl } = useEnvironment();
  const [nestedNode, setNestedNode] = useState<Document>();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const id = isStandard ? node.name : node.id;

  var usedNode = nestedNode || node;
  const hasExternalLink = Boolean(usedNode.hyperlink);
  const linksByType = useMemo(() => groupLinksByType(usedNode), [usedNode]);

  useEffect( () => {
    if ( !isStandard && linkTypesToNest.includes(linkType) ) {
      setLoading(true);
      axios.get(getApiEndpoint(node, apiUrl))
      .then(function (response) {
        setLoading(false);
        setNestedNode(response.data.data);
        setExpanded(true);
        setError('');
      })
      .catch(function (axiosError) {
        setLoading(false);
        setError(axiosError);
      });
    }
  }, [id]);

  if ( ( !usedNode.links || usedNode.links.length === 0)) {
    return (
      <>
        <div className={`title external-link document-node f2`}>
          <Link to={getInternalUrl(usedNode)}>
            <i aria-hidden="true" className="circle icon"></i>
            { getDocumentDisplayName(usedNode) }
          </Link>
        </div>
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
        <Link to={getInternalUrl(usedNode)}>
          { getDocumentDisplayName(usedNode) }
        </Link>
      </div>
      <div className={`content${active} document-node`}>
        { expanded && hasExternalLink &&
          <>
            <span>
              Reference: 
            </span>
            <a href={usedNode.hyperlink} target="_blank"> { usedNode.hyperlink }</a>
          </>
        }
        { expanded 
          && Object.entries(linksByType)
            .filter( ([type, _]) => !linkTypesExcludedInNesting.includes(type) )
            .map( ([type, links] ) => {
            return (
              <div className="document-node__link-type-container" key={type}>
                <div>
                  <span > {usedNode.name} - {usedNode.section} </span>
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
