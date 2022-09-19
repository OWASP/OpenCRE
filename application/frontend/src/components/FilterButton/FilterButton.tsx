import axios from 'axios';
import React, { FunctionComponent, useEffect, useMemo, useState } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { Button } from 'semantic-ui-react';

import {
  DOCUMENT_TYPE_NAMES,
  TYPE_CONTAINS,
  TYPE_IS_PART_OF,
  TYPE_LINKED_TO,
  TYPE_RELATED,
} from '../../const';
import { useEnvironment } from '../../hooks';
import { Document, LinkedDocument } from '../../types';
import { getDocumentDisplayName, groupLinksByType } from '../../utils';
import { getApiEndpoint, getInternalUrl } from '../../utils/document';
import { LoadingAndErrorIndicator } from '../LoadingAndErrorIndicator';

export interface FilterButton {
  document: Document;
}

export const ClearFilterButton: FunctionComponent = (props) => {
  let currentUrlParams = new URLSearchParams(window.location.search);
  const history = useHistory();

  const ClearFilter = () => {
    currentUrlParams.set('applyFilters', 'false');
    currentUrlParams.delete('filters');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
    window.location.href = window.location.href;
  };

  return (
    <div id="clearFilterButton">
      <Button
        onClick={() => {
          ClearFilter();
        }}
        content="Clear Filters"
      ></Button>
    </div>
  );
};

export const FilterButton: FunctionComponent<FilterButton> = (props) => {
  let document = props.document;
  const [filters, setFilters] = useState<string[]>();
  let currentUrlParams = new URLSearchParams(window.location.search);
  const history = useHistory();

  const handleFilter = (document: Document) => {
    var fltrs;
    if (document.doctype == 'CRE') {
      fltrs = filters && filters.length ? new Set([...filters, '' + document.id]) : ['' + document.id];
      // fltrs = filters && filters.length ? new Set([...filters, "c:" + document.id]) : ["c:" + document.id]
    } else if (document.doctype in ['Tool', 'Code', 'Standard']) {
      fltrs = filters && filters.length ? new Set([...filters, '' + document.name]) : ['' + document.name];
      // fltrs = filters && filters.length ? new Set([...filters, "s:" + document.name]) : ["s:" + document.name]
    }
    fltrs.forEach((f) => {
      if (!currentUrlParams.getAll('filters').includes(f)) {
        currentUrlParams.append('filters', f);
      }
    });
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
    setFilters(Array.from(fltrs));
  };
  if (currentUrlParams.has('showButtons')) {
    return document.doctype in ['Tool', 'Code', 'Standard'] ? (
      <Button
        onClick={() => {
          handleFilter(document);
        }}
        content="Filter this item"
      ></Button>
    ) : (
      <></>
    );
  }
  return <></>;
};
