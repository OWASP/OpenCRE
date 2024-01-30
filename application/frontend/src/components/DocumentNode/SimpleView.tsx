import React, { FunctionComponent } from 'react';
import { Link } from 'react-router-dom';

import { Document } from '../../types';
import { getDocumentDisplayName } from '../../utils';
import { getInternalUrl } from '../../utils/document';
import HyperLinkIcon from '../hyper-links/hyper-link-icon/HyperLinkIcon';

export interface SimpleView {
  usedNode: Document;
}

const SimpleView: FunctionComponent<SimpleView> = ({ usedNode }) => {
  return (
    <>
      <div className={`title external-link document-node f2`}>
        <Link to={getInternalUrl(usedNode)}>
          <i aria-hidden="true" className="circle icon"></i>
          {getDocumentDisplayName(usedNode)}
        </Link>
        <HyperLinkIcon hyperLink={usedNode.hyperlink} />
      </div>
      <div className={`content`}></div>
    </>
  );
};

export default SimpleView;
