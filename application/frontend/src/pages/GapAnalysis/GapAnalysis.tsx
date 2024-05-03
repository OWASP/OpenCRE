import axios from 'axios';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Button, Dropdown, DropdownItemProps, Icon, Popup, Table } from 'semantic-ui-react';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { GA_STRONG_UPPER_LIMIT } from '../../const';
import { useEnvironment } from '../../hooks';
import { GapAnalysisPathStart } from '../../types';
import { getDocumentDisplayName } from '../../utils';
import { getInternalUrl } from '../../utils/document';

const GetSegmentText = (segment, segmentID) => {
  let textPart = segment.end;
  let nextID = segment.end.id;
  let arrow = <Icon name="arrow down" />;
  if (segmentID !== segment.start.id) {
    textPart = segment.start;
    nextID = segment.start.id;
    arrow = <Icon name="arrow up" />;
  }
  const text = (
    <>
      <br />
      {arrow}{' '}
      <span style={{ textTransform: 'capitalize' }}>
        {segment.relationship.replace('_', ' ').toLowerCase()} {segment.score > 0 && <> (+{segment.score})</>}
      </span>
      <br /> {getDocumentDisplayName(textPart, true)} {textPart.section ?? ''} {textPart.subsection ?? ''}{' '}
      {textPart.description ?? ''}
    </>
  );
  return { text, nextID };
};

function useQuery() {
  const { search } = useLocation();

  return React.useMemo(() => new URLSearchParams(search), [search]);
}

const GetStrength = (score) => {
  if (score == 0) return 'Direct';
  if (score <= GA_STRONG_UPPER_LIMIT) return 'Strong';
  if (score >= 20) return 'Weak';
  return 'Average';
};

const GetStrengthColor = (score) => {
  if (score === 0) return 'darkgreen';
  if (score <= GA_STRONG_UPPER_LIMIT) return '#93C54B';
  if (score >= 20) return 'Red';
  return 'Orange';
};

const GetResultLine = (path, gapAnalysis, key) => {
  let segmentID = gapAnalysis[key].start.id;
  return (
    <div key={path.end.id} style={{ marginBottom: '.25em', fontWeight: 'bold' }}>
      <a href={getInternalUrl(path.end)} target="_blank">
        <Popup
          wide="very"
          size="large"
          style={{ textAlign: 'center' }}
          hoverable
          trigger={<span>{getDocumentDisplayName(path.end, true)} </span>}
        >
          <Popup.Content>
            {getDocumentDisplayName(gapAnalysis[key].start, true)}
            {path.path.map((segment) => {
              const { text, nextID } = GetSegmentText(segment, segmentID);
              segmentID = nextID;
              return text;
            })}
          </Popup.Content>
        </Popup>
        <Popup
          wide="very"
          size="large"
          style={{ textAlign: 'center' }}
          hoverable
          trigger={
            <b style={{ color: GetStrengthColor(path.score) }}>
              ({GetStrength(path.score)}:{path.score})
            </b>
          }
        >
          <Popup.Content>
            <b>Generally: lower is better</b>
            <br />
            <b style={{ color: GetStrengthColor(0) }}>{GetStrength(0)}</b>: Directly Linked
            <br />
            <b style={{ color: GetStrengthColor(GA_STRONG_UPPER_LIMIT) }}>
              {GetStrength(GA_STRONG_UPPER_LIMIT)}
            </b>
            : Closely connected likely to have majority overlap
            <br />
            <b style={{ color: GetStrengthColor(6) }}>{GetStrength(6)}</b>: Connected likely to have partial
            overlap
            <br />
            <b style={{ color: GetStrengthColor(22) }}>{GetStrength(22)}</b>: Weakly connected likely to have
            small or no overlap
          </Popup.Content>
        </Popup>
      </a>
    </div>
  );
};

export const GapAnalysis = () => {
  const standardOptionsDefault = [{ key: '', text: '', value: undefined }];
  const searchParams = useQuery();
  const [standardOptions, setStandardOptions] = useState<DropdownItemProps[] | undefined>(
    standardOptionsDefault
  );
  const [BaseStandard, setBaseStandard] = useState<string | undefined>(searchParams.get('base') ?? '');
  const [CompareStandard, setCompareStandard] = useState<string | undefined>(
    searchParams.get('compare') ?? ''
  );
  const [gaJob, setgaJob] = useState<string>('');
  const [gapAnalysis, setGapAnalysis] = useState<Record<string, GapAnalysisPathStart>>();
  const [loadingStandards, setLoadingStandards] = useState<boolean>(false);
  const [loadingGA, setLoadingGA] = useState<boolean>(false);
  const [error, setError] = useState<string | null | object>(null);
  const { apiUrl } = useEnvironment();
  const timerIdRef = useRef<NodeJS.Timer>();

  useEffect(() => {
    const fetchData = async () => {
      const result = await axios.get(`${apiUrl}/standards`);
      setLoadingStandards(false);
      setStandardOptions(
        standardOptionsDefault.concat(result.data.sort().map((x) => ({ key: x, text: x, value: x })))
      );
    };

    setLoadingStandards(true);
    fetchData().catch((e) => {
      setLoadingStandards(false);
      setError(e.response.data.message ?? e.message);
    });
  }, [setStandardOptions, setLoadingStandards, setError]);

  useEffect(() => {
    console.log('gajob changed, polling');
    const pollingCallback = () => {
      const fetchData = async () => {
        const result = await axios.get(`${apiUrl}/ma_job_results?id=` + gaJob, {
          headers: {
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
            Expires: '0',
          },
        });
        if (result.data.result) {
          setLoadingGA(false);
          setGapAnalysis(result.data.result);
          setgaJob('');
        }
      };
      if (!gaJob) return;
      fetchData().catch((e) => {
        setLoadingGA(false);
        setError(e.response.data.message ?? e.message);
      });
    };

    const startPolling = () => {
      // Polling every 10 seconds
      timerIdRef.current = setInterval(pollingCallback, 10000);
    };
    const stopPolling = () => {
      clearInterval(timerIdRef.current);
    };

    if (gaJob) {
      console.log('started polling');
      startPolling();
    } else {
      console.log('stoped polling');
      stopPolling();
    }

    return () => {
      stopPolling();
    };
  }, [gaJob]);

  useEffect(() => {
    const fetchData = async () => {
      const result = await axios.get(
        `${apiUrl}/map_analysis?standard=${BaseStandard}&standard=${CompareStandard}`
      );
      if (result.data.result) {
        setLoadingGA(false);
        setGapAnalysis(result.data.result);
      } else if (result.data.job_id) {
        setgaJob(result.data.job_id);
      }
    };

    if (!BaseStandard || !CompareStandard || BaseStandard === CompareStandard) return;
    setGapAnalysis(undefined);
    setLoadingGA(true);
    fetchData().catch((e) => {
      setLoadingGA(false);
      setError(e.response.data.message ?? e.message);
    });
  }, [BaseStandard, CompareStandard, setGapAnalysis, setLoadingGA, setError]);

  const getWeakLinks = useCallback(
    async (key) => {
      if (!gapAnalysis) return;
      const result = await axios.get(
        `${apiUrl}/map_analysis_weak_links?standard=${BaseStandard}&standard=${CompareStandard}&key=${key}`
      );
      if (result.data.result) {
        gapAnalysis[key].weakLinks = result.data.result.paths;
        setGapAnalysis(undefined); //THIS HAS TO BE THE WRONG WAY OF DOING THIS
        setGapAnalysis(gapAnalysis);
      }
    },
    [gapAnalysis, setGapAnalysis]
  );

  return (
    <div style={{ padding: '30px' }}>
      <h1 className="standard-page__heading">Map Analysis</h1>
      <Table celled padded compact>
        <Table.Header>
          <Table.Row>
            <Table.HeaderCell>
              {' '}
              Base:{' '}
              <Dropdown
                placeholder="Base Standard"
                search
                selection
                options={standardOptions}
                onChange={(e, { value }) => setBaseStandard(value?.toString())}
                value={BaseStandard}
              />
            </Table.HeaderCell>
            <Table.HeaderCell>
              Compare:{' '}
              <Dropdown
                placeholder="Compare Standard"
                search
                selection
                options={standardOptions}
                onChange={(e, { value }) => setCompareStandard(value?.toString())}
                value={CompareStandard}
              />
              {gapAnalysis && (
                <div style={{ float: 'right' }}>
                  <Button
                    onClick={() => {
                      navigator.clipboard.writeText(
                        `${window.location.origin}/map_analysis?base=${encodeURIComponent(
                          BaseStandard || ''
                        )}&compare=${encodeURIComponent(CompareStandard || '')}`
                      );
                    }}
                    target="_blank"
                  >
                    <Icon name="share square" /> Copy link to analysis
                  </Button>
                </div>
              )}
            </Table.HeaderCell>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          <LoadingAndErrorIndicator loading={loadingGA || loadingStandards} error={error} />
          {gapAnalysis && (
            <>
              {Object.keys(gapAnalysis)
                .sort((a, b) =>
                  getDocumentDisplayName(gapAnalysis[a].start, true).localeCompare(
                    getDocumentDisplayName(gapAnalysis[b].start, true)
                  )
                )
                .map((key) => (
                  <Table.Row key={key}>
                    <Table.Cell textAlign="left" verticalAlign="top" selectable>
                      <a href={getInternalUrl(gapAnalysis[key].start)} target="_blank">
                        <p>
                          <b>{getDocumentDisplayName(gapAnalysis[key].start, true)}</b>
                        </p>
                      </a>
                    </Table.Cell>
                    <Table.Cell style={{ minWidth: '35vw' }}>
                      {Object.values<any>(gapAnalysis[key].paths)
                        .sort((a, b) => a.score - b.score)
                        .map((path) => GetResultLine(path, gapAnalysis, key))}
                      {gapAnalysis[key].weakLinks &&
                        Object.values<any>(gapAnalysis[key].weakLinks)
                          .sort((a, b) => a.score - b.score)
                          .map((path) => GetResultLine(path, gapAnalysis, key))}
                      {gapAnalysis[key].extra > 0 && !gapAnalysis[key].weakLinks && (
                        <Button onClick={async () => await getWeakLinks(key)}>
                          Show average and weak links ({gapAnalysis[key].extra})
                        </Button>
                      )}
                      {Object.keys(gapAnalysis[key].paths).length === 0 && gapAnalysis[key].extra === 0 && (
                        <i>No links Found</i>
                      )}
                    </Table.Cell>
                  </Table.Row>
                ))}
            </>
          )}
        </Table.Body>
      </Table>
    </div>
  );
};
