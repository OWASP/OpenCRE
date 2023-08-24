import './browseRootCres.scss';

import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';

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
  const { error, data, refetch } = useQuery<{ data: Document }, string>(
    'cre',
    () =>
      fetch(`${apiUrl}/root_cres`)
        .then((res) => res.json())
        .then((resjson) => {
          setDisplay(resjson.data);
          return resjson;
        }),
    {
      retry: false,
      enabled: false,
      onSettled: () => {
        setLoading(false);
      },
    }
  );

  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    refetch();
  }, []);

  return (
    <div className="cre-page">
      <h1 className="standard-page__heading">Root CREs:</h1>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {!loading && !error && (
        <div className="ui grid">
          <div className="wide column">{display && <SearchResults results={display} />}</div>
        </div>
      )}
    </div>
  );
};
