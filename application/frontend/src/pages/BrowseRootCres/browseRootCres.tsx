import './browseRootCres.scss';

import React, { useEffect, useMemo, useState, useContext } from 'react';
import { useQuery } from 'react-query';
import { useParams } from 'react-router-dom';

import { DocumentNode } from '../../components/DocumentNode';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { DOCUMENT_TYPE_NAMES } from '../../const';
import { useEnvironment } from '../../hooks';
import { Document } from '../../types';
import { groupLinksByType } from '../../utils';
import { applyFilters, filterContext } from '../../hooks/applyFilters';
import { ClearFilterButton, FilterButton } from '../../components/FilterButton/FilterButton';
import { SearchResults } from '../Search/components/SearchResults';

export const BrowseRootCres = () => {
  const { id } = useParams();
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const globalState = useContext(filterContext)

  const { error, data, refetch } = useQuery<{ data: Document; }, string>(
    'cre',
    () => fetch(`${apiUrl}/root_cres`).then((res) => res.json()),
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
  }, [id]);

  // TODO: the rest should really be shared between this and CommonRequirementEnumeration instead of ugly copy pastes

  const cre = data?.data;
  let display = cre
  console.log(display)
  return (
    <div className="cre-page">
        <h1 className="standard-page__heading">
            Root Cres:
        </h1>
        <LoadingAndErrorIndicator loading={loading} error={error} />
        {!loading && !error &&
            <div className="ui grid">
                <div className="wide column">
                    <h1 className="standard-page__heading">Related CRE's</h1>
                    {display && <SearchResults results={display}/>}
                </div>
            </div>
        }
    </div>
  );
};
