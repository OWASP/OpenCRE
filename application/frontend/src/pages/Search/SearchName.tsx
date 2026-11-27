import axios from 'axios';
import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Message } from 'semantic-ui-react';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';
import { scrollMountToTop } from '../../utils';
import { groupBy } from '../../utils/document';
import { SearchResults } from './components/SearchResults';

const CRE = 'CRE';
const NODES = ['Standard', 'Tool', 'Code'];

export const SearchName = () => {
  const { searchTerm } = useParams<{ searchTerm: string }>();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | Object | null>(null);

  useEffect(() => {
    scrollMountToTop();
    setLoading(true);
    axios
      .get(`${apiUrl}/text_search`, { params: { text: searchTerm } })
      .then(function (response) {
        setError(null);
        setDocuments(response.data);
      })
      .catch(function (axiosError) {
        // TODO: backend errors if no matches, should return
        //       proper error instead.
        if (axiosError.response.status === 404) {
          setError('No results match your search term');
        } else {
          setError(axiosError.response);
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, [searchTerm]);

  const groupedByType = groupBy(documents, (doc) => doc.doctype);
  Object.keys(groupedByType).forEach((key) => {
    groupedByType[key] = groupedByType[key].sort((a, b) =>
      (a.name + a.section).localeCompare(b.name + b.section)
    );
  });
  const cres = groupedByType[CRE];

  let nodes;
  for (var NODE of NODES) {
    if (groupedByType[NODE]) {
      nodes = nodes ? nodes.concat(groupedByType[NODE]) : groupedByType[NODE];
    }
  }

  const hasCres = Boolean(cres && cres.length > 0);
  const hasNodes = Boolean(nodes && nodes.length > 0);
  const hasResults = hasCres || hasNodes;

  return (
    <div className="cre-page">
      <h1 className="standard-page__heading">
        Results matching : <i>{searchTerm}</i>
      </h1>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && (
        <>
          {!hasResults ? (
            <Message info>
              <Message.Header>No results match your search.</Message.Header>
              <p>No CREs or sources were found for &ldquo;{searchTerm}&rdquo;.</p>
            </Message>
          ) : (
            <div className="ui grid">
              <div className="eight wide column">
                <h1 className="standard-page__heading">Matching CREs</h1>
                {hasCres ? (
                  <SearchResults results={cres} />
                ) : (
                  <Message info>No CREs match this search.</Message>
                )}
              </div>
              <div className="eight wide column">
                <h1 className="standard-page__heading">Matching sources</h1>
                {hasNodes ? (
                  <SearchResults results={nodes} />
                ) : (
                  <Message info>No sources match this search.</Message>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
