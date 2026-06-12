import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';
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
    if (!searchTerm?.trim()) {
      setDocuments([]);
      setError('Search term cannot be blank');
      setLoading(false);
      return;
    }

    setLoading(true);
    axios
      .get(`${apiUrl}/text_search`, { params: { text: searchTerm } })
      .then(function (response) {
        setError(null);
        setDocuments(response.data);
      })
      .catch(function (axiosError) {
        const status = axiosError.response?.status;
        if (status === 404) {
          setError('No results match your search term');
        } else if (status === 400) {
          const message = axiosError.response?.data?.error;
          setError(
            typeof message === 'string' ? message : 'Invalid search request'
          );
        } else {
          setError('Document could not be loaded');
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, [apiUrl, searchTerm]);

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

  return (
    <div className="cre-page">
      <h1 className="standard-page__heading">
        Results matching : <i>{searchTerm}</i>
      </h1>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && (
        <div className="ui grid">
          <div className="eight wide column">
            <h1 className="standard-page__heading">Matching CREs</h1>
            {cres && <SearchResults results={cres} />}
          </div>
          <div className="eight wide column">
            <h1 className="standard-page__heading">Matching sources</h1>
            {nodes && <SearchResults results={nodes} />}
          </div>
        </div>
      )}
    </div>
  );
};
