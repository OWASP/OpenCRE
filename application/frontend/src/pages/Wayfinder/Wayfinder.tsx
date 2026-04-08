import './wayfinder.scss';

import axios from 'axios';
import React, { useEffect, useMemo, useState } from 'react';
import { Button, Dropdown, Input, Label } from 'semantic-ui-react';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';
import { WayfinderFacet, WayfinderResource, WayfinderResponse } from '../../types';

const toArray = (
  value: string | number | boolean | (string | number | boolean)[] | undefined
): string[] => {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map((entry) => String(entry));
  }
  return [String(value)];
};

const asOptions = (facets: WayfinderFacet[] = []) =>
  facets.map((facet) => ({
    key: facet.value,
    text: `${facet.value} (${facet.count})`,
    value: facet.value,
  }));

export const Wayfinder = () => {
  const { apiUrl } = useEnvironment();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<WayfinderResponse | null>(null);

  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [selectedSdlc, setSelectedSdlc] = useState<string[]>([]);
  const [selectedOrgs, setSelectedOrgs] = useState<string[]>([]);
  const [selectedLicenses, setSelectedLicenses] = useState<string[]>([]);
  const [selectedDoctypes, setSelectedDoctypes] = useState<string[]>([]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [query]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const params: Record<string, string | string[]> = {};
        if (debouncedQuery) params.q = debouncedQuery;
        if (selectedSdlc.length) params.sdlc = selectedSdlc;
        if (selectedOrgs.length) params.supporting_org = selectedOrgs;
        if (selectedLicenses.length) params.license = selectedLicenses;
        if (selectedDoctypes.length) params.doctype = selectedDoctypes;

        const res = await axios.get<WayfinderResponse>(`${apiUrl}/wayfinder`, { params });
        setResponse(res.data);
      } catch (err) {
        console.error(err);
        setError('Could not load wayfinder data');
      } finally {
        setLoading(false);
      }
    };

    load();
  }, [apiUrl, debouncedQuery, selectedDoctypes, selectedLicenses, selectedOrgs, selectedSdlc]);

  const stats = response?.stats;
  const groups = response?.grouped_by_sdlc || [];

  const sdlcOptions = useMemo(() => asOptions(response?.facets?.sdlc), [response?.facets?.sdlc]);
  const orgOptions = useMemo(
    () => asOptions(response?.facets?.supporting_orgs),
    [response?.facets?.supporting_orgs]
  );
  const licenseOptions = useMemo(
    () => asOptions(response?.facets?.licenses),
    [response?.facets?.licenses]
  );
  const doctypeOptions = useMemo(
    () => asOptions(response?.facets?.doctypes),
    [response?.facets?.doctypes]
  );

  const clearFilters = () => {
    setQuery('');
    setSelectedSdlc([]);
    setSelectedOrgs([]);
    setSelectedLicenses([]);
    setSelectedDoctypes([]);
  };

  const renderResourceCard = (resource: WayfinderResource) => (
    <article className="wayfinder-card" key={`${resource.id}-${resource.name}`}>
      <div className="wayfinder-card__header">
        <h3>{resource.name}</h3>
        <Label size="tiny" color="blue">
          {resource.doctype}
        </Label>
      </div>

      <div className="wayfinder-card__meta">
        <div>
          <strong>Supporting org:</strong> {resource.metadata.supporting_orgs.join(', ')}
        </div>
        <div>
          <strong>License:</strong> {resource.metadata.licenses.join(', ')}
        </div>
      </div>

      <div className="wayfinder-card__footer">
        <span>{resource.entry_count} mapped entries</span>
        {resource.hyperlink ? (
          <a href={resource.hyperlink} target="_blank" rel="noopener noreferrer">
            Open source
          </a>
        ) : (
          <span className="wayfinder-card__muted">No direct link</span>
        )}
      </div>
    </article>
  );

  return (
    <main id="wayfinder-content">
      <section className="wayfinder-intro">
        <h1>Product Security Wayfinder</h1>
        <p>
          Explore standards and tools known to OpenCRE by SDLC stage, then narrow the view using metadata
          facets.
        </p>
        <div className="wayfinder-stats">
          <div>
            <span>Total resources</span>
            <strong>{stats?.total_resources || 0}</strong>
          </div>
          <div>
            <span>Filtered resources</span>
            <strong>{stats?.filtered_resources || 0}</strong>
          </div>
          <div>
            <span>Mapped entries</span>
            <strong>{stats?.filtered_entries || 0}</strong>
          </div>
        </div>
      </section>

      <section className="wayfinder-filters">
        <Input
          fluid
          placeholder="Search resource name or keyword..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="wayfinder-filter-grid">
          <Dropdown
            fluid
            multiple
            search
            selection
            placeholder="SDLC phases"
            options={sdlcOptions}
            value={selectedSdlc}
            onChange={(_, data) => setSelectedSdlc(toArray(data.value))}
          />
          <Dropdown
            fluid
            multiple
            search
            selection
            placeholder="Supporting organizations"
            options={orgOptions}
            value={selectedOrgs}
            onChange={(_, data) => setSelectedOrgs(toArray(data.value))}
          />
          <Dropdown
            fluid
            multiple
            search
            selection
            placeholder="Licenses"
            options={licenseOptions}
            value={selectedLicenses}
            onChange={(_, data) => setSelectedLicenses(toArray(data.value))}
          />
          <Dropdown
            fluid
            multiple
            search
            selection
            placeholder="Resource type"
            options={doctypeOptions}
            value={selectedDoctypes}
            onChange={(_, data) => setSelectedDoctypes(toArray(data.value))}
          />
        </div>
        <Button basic size="small" onClick={clearFilters}>
          Clear filters
        </Button>
      </section>

      <LoadingAndErrorIndicator loading={loading} error={error} />

      {!loading && !error && (
        <section className="wayfinder-lanes">
          {groups.map((group) => (
            <section className="wayfinder-lane" key={group.phase}>
              <div className="wayfinder-lane__header">
                <h2>{group.phase}</h2>
                <span>{group.resources.length} resources</span>
              </div>

              <div className="wayfinder-lane__cards">
                {group.resources.length > 0 ? (
                  group.resources.map((resource) => renderResourceCard(resource))
                ) : (
                  <div className="wayfinder-lane__empty">No resources for this lane with current filters.</div>
                )}
              </div>
            </section>
          ))}
        </section>
      )}
    </main>
  );
};
