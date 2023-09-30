import './explorer.scss';

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

export const Explorer = () => {
  const { apiUrl } = useEnvironment();
  const [loading, setLoading] = useState<boolean>(false);
  const [filter, setFilter] = useState("");
  const [searchSummary, setSearchSummary] = useState(0);
  const [data, setData] = useState<Document[]>()
  const [rootCREs, setRootCREs] = useState<Document[]>()
  const [filteredData, setFilteredData] = useState<Document[]>()

  useQuery<{ data: Document }, string>(
    'root_cres',
    () =>
      fetch(`${apiUrl}/root_cres`)
        .then((res) => res.json())
        .then((resjson) => {
          setRootCREs(resjson.data);
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
  const docs = localStorage.getItem("documents")
  useEffect(()=>{
    if (docs != null) {
      setData(JSON.parse(docs).sort((a, b) => (a.id + '').localeCompare(b.id + '')));
      setFilteredData(data)
    }
  },[docs])
  
  const query = useQuery(
    'everything',
    () => {
      if (docs == null) {
        fetch(`${apiUrl}/everything`)
          .then((res) => { return res.json() })
          .then((resjson) => {
            return resjson.data
          }).then((data) => {
            if (data) {
              localStorage.setItem("documents", JSON.stringify(data));
              setData(data)
            }
          }),
        {
          retry: false,
          enabled: false,
          onSettled: () => {
            setLoading(false);
          },
        }
      }

    }
  );


  useEffect(() => {
    window.scrollTo(0, 0);
    setLoading(true);
    query.refetch();
  }, []);


  if (!data?.length) {
    const docs = localStorage.getItem("documents")
    if (docs) {
      setData(JSON.parse(docs).sort((a, b) => (a.id + '').localeCompare(b.id + '')));
      setFilteredData(data)
    }
  }

  function processNode(item) {
    if (!item) {
      return (<></>)
    }
    return (
      <div className="group" >
        <div className="group-1">
          <div className='group-2'>
            <a target="_blank" href={"https://opencre.org/cre/" + item?.id}>
              {item?.name}
            </a>
          </div>
          <div /*style="font-size: 90%"*/>
            {item?.links?.forEach(child => processNode(child))}
          </div>
        </div>
      </div>
    )
  }
  function update(event) {
    setFilter(event.target.value)
    setFilteredData(data?.filter(item => item.name.toLowerCase().includes(filter)))
  }

  return (<>
    {/* <LoadingAndErrorIndicator loading={loading} error={query.error} /> */}
    <div id="explorer-content">
      <h1>
        <img src="assets/logo.png" />
        <b>Open CRE Explorer</b>
      </h1>
      <p>A visual explorer of Open Common Requirement Enumerations (CREs).
        Data source: <a target="_blank" href="https://opencre.org/">opencre.org</a>.</p>

      <div id="explorer-wrapper">
        <div>
          <input id="filter" type="text" placeholder="search..."
            onKeyUp={update} />
          <div id="search-summary"></div>
        </div>
        <div id="graphs">graphs (3D):
          <a target="_blank" href="visuals/force-graph-3d-all.html">CRE dependencies</a> -
          <a target="_blank" href="visuals/force-graph-3d-contains.html">hierarchy only</a> -
          <a target="_blank" href="visuals/force-graph-3d-related.html">related only</a> |
          <a target="_blank" href="visuals/force-graph-3d-linked.html">links to external standards</a> |
          <a target="_blank" href="visuals/circles.html">zoomable circles</a>
        </div>
      </div>
      <div id="content"></div>
      {filteredData?.map(item => {
        return processNode(item)
      })}
    </div>

  </>
  );
};
