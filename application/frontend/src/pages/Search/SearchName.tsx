import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

import { useEnvironment } from '../../hooks';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { groupBy } from '../../utils/document';
import { Document } from '../../types';

import { SearchResults } from './components/SearchResults';

const CRE = "CRE";
const STANDARD = "Standard";

export const SearchName = () => {
  const { searchTerm } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    axios.get(`${apiUrl}/text_search`, {params: {text: searchTerm}})
        .then(function (response) {
            setError(null);
            setDocuments(response.data);
        })
        .catch(function (axiosError) {
            // TODO: backend errors if no matches, shoudl return
            //       proper error instead.
            setError(axiosError);
        }).finally( () => {
            setLoading(false);
        });
  }, [searchTerm]);

  const groupedByType = groupBy(documents, doc => doc.doctype);

  return (
    <div className="cre-page">
        <h1 className="standard-page__heading">
            Results matching : <i>{searchTerm}</i>
        </h1>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        {!loading && !error &&
            <div className="ui grid">
                <div className="eight wide column">
                    <h1 className="standard-page__heading">Related CRE's</h1>
                    {groupedByType[CRE] && <SearchResults results={groupedByType[CRE]}/>}
                </div>
                <div className="eight wide column">
                    <h1 className="standard-page__heading">Related standards</h1>
                    {groupedByType[STANDARD] && <SearchResults results={groupedByType[STANDARD]}/>}
                </div>
            </div>
        }
    </div>
  );
};
