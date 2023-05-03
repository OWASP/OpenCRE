import React from 'react';

import { DocumentNode } from '../../../components/DocumentNode';

export const SearchResults = ({ results }) => {
  if (results && results.length != 0) {
    return (
      <>
        {results.map((document, i) => (
          <div key={i} className="accordion ui fluid styled standard-page__links-container">
            <DocumentNode node={document} linkType={'Standard'} />
          </div>
        ))}
      </>
    )
  }
  return <></>
};
