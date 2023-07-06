import React from 'react';

import { DocumentNode } from '../../../components/DocumentNode';
import { getDocumentDisplayName } from 'application/frontend/src/utils/document';

export const SearchResults = ({ results, grouped=false }) => {
  if (results && results.length != 0) {
    const sortedResults = results.sort((a, b) => getDocumentDisplayName(a).localeCompare(getDocumentDisplayName(b)))
    let lastDocumentName = sortedResults[0].id ?? sortedResults[0].name
    return (
      <>
        {sortedResults.map((document, i) => {let temp = (
          <>
            {grouped && lastDocumentName !== (document.id ?? document.name) &&<hr style={{marginBottom: "40px"}} />}
            <div key={i} className="accordion ui fluid styled standard-page__links-container">
              <DocumentNode node={document} linkType={'Standard'} />
            </div>
          </>
        
        )
        lastDocumentName = (document.id ?? document.name);
        return temp
        })}
      </>
    );
  }
  return <></>;
};
