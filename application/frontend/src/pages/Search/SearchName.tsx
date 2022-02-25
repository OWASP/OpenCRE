import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import ExportButton from '../../components/ExportButton/export-button';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';
import { groupBy } from '../../utils/document';
import { SearchResults } from './components/SearchResults';

const CRE = 'CRE';
const STANDARD = 'Standard';

export const SearchName = () => {
  const { searchTerm } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);

  const FETCH_URL = `${apiUrl}/text_search`;
  const FETCH_PARAMS = { params: { text: searchTerm } };

  useEffect(() => {
    setLoading(true);
    axios
      .get(FETCH_URL, FETCH_PARAMS)
      .then(function (response) {
        setError(null);
        setDocuments(response.data);
      })
      .catch(function (axiosError) {
        // TODO: backend errors if no matches, shoudl return
        //       proper error instead.
        setError(axiosError);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [searchTerm]);

  const groupedByType = groupBy(documents, (doc) => doc.doctype);

  return (
    <div className="cre-page">
      <h1 className="standard-page__heading">
        Results matching : <i>{searchTerm}</i>
      </h1>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && (
        <div className="ui grid">
          <div className="eight wide column">
            <h1 className="standard-page__heading">
              Related CRE's
              <ExportButton fetchURL={FETCH_URL} fetchParams={FETCH_PARAMS} />
            </h1>
            {groupedByType[CRE] && <SearchResults results={groupedByType[CRE]} />}
          </div>
          <div className="eight wide column">
            <h1 className="standard-page__heading">Related Documents</h1>
            {groupedByType[STANDARD] && <SearchResults results={groupedByType[STANDARD]} />}
          </div>
        </div>
      )}
    </div>
  );
};
