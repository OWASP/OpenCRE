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
  const { searchTerm } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | Object | null>(null);

  useEffect(() => {
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
