import './browseRootCres.scss';

import axios from 'axios';
import React, { useContext, useEffect, useMemo, useState } from 'react';

import { DocumentNode } from '../../components/DocumentNode';
import { ClearFilterButton, FilterButton } from '../../components/FilterButton/FilterButton';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { applyFilters, filterContext } from '../../hooks/applyFilters';
import { Document } from '../../types';
import { groupLinksByType } from '../../utils';
import { SearchResults } from '../Search/components/SearchResults';

export const BrowseRootCres = () => {
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [display, setDisplay] = useState<Document[]>();
  const [error, setError] = useState<string | Object | null>(null);

  useEffect(() => {
    setLoading(true);
    window.scrollTo(0, 0);

    axios
      .get(`${apiUrl}/root_cres`)
      .then(function (response) {
        setError(null);
        setDisplay(response?.data?.data);
      })
      .catch(function (axiosError) {
        if (axiosError.response.status === 404) {
          setError('Standard does not exist in the DB, please check your search parameters');
        } else {
          setError(axiosError.response);
        }
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);
  return (
    <div className="cre-page">
      <h1 className="standard-page__heading">Root CREs</h1>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && (
        <div className="ui grid">
          <div className="wide column">{display && <SearchResults results={display} />}</div>
        </div>
      )}
    </div>
  );
};
