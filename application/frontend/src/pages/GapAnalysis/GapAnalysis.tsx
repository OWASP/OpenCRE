import axios from 'axios';
import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Accordion,
  Button,
  Container,
  Dropdown,
  DropdownItemProps,
  Grid,
  Icon,
  Label,
  Popup,
  Table,
} from 'semantic-ui-react';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
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
  if (score <= 2) return 'Strong';
  if (score >= 20) return 'Weak';
  return 'Average';
};

const GetStrengthColor = (score) => {
  if (score === 0) return 'darkgreen';
  if (score <= 2) return '#93C54B';
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
            <b style={{ color: GetStrengthColor(2) }}>{GetStrength(2)}</b>: Closely connected likely to have
            majority overlap
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
  const [gapAnalysis, setGapAnalysis] = useState<Record<string, GapAnalysisPathStart>>();
  const [activeIndex, SetActiveIndex] = useState<string>();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null | object>(null);
  const { apiUrl } = useEnvironment();

  const GetStrongPathsCount = (paths) =>
    Math.max(
      Object.values<any>(paths).filter(
        (x) => GetStrength(x.score) === 'Strong' || GetStrength(x.score) === 'Direct'
      ).length,
      3
    );

  useEffect(() => {
    const fetchData = async () => {
      const result = await axios.get(`${apiUrl}/standards`);
      setLoading(false);
      setStandardOptions(
        standardOptionsDefault.concat(result.data.sort().map((x) => ({ key: x, text: x, value: x })))
      );
    };

    setLoading(true);
    fetchData().catch((e) => {
      setLoading(false);
      setError(e.response.data.message ?? e.message);
    });
  }, [setStandardOptions, setLoading, setError]);

  useEffect(() => {
    const fetchData = async () => {
      const result = await axios.get(
        `${apiUrl}/map_analysis?standard=${BaseStandard}&standard=${CompareStandard}`
      );
      setLoading(false);
      setGapAnalysis(result.data);
    };

    if (!BaseStandard || !CompareStandard || BaseStandard === CompareStandard) return;
    setGapAnalysis(undefined);
    setLoading(true);
    fetchData().catch((e) => {
      setLoading(false);
      setError(e.response.data.message ?? e.message);
    });
  }, [BaseStandard, CompareStandard, setGapAnalysis, setLoading, setError]);

  const handleAccordionClick = (e, titleProps) => {
    const { index } = titleProps;
    const newIndex = activeIndex === index ? -1 : index;
    SetActiveIndex(newIndex);
  };

  return (
    <div style={{ margin: '0 auto', maxWidth: '95vw' }}>
      <Table celled padded compact style={{ margin: '5px' }}>
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
                    <Icon name="share square" /> Share this anyalysis
                  </Button>
                </div>
              )}
            </Table.HeaderCell>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          <LoadingAndErrorIndicator loading={loading} error={error} />
          {gapAnalysis && (
            <>
              {Object.keys(gapAnalysis).map((key) => (
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
                      .slice(0, GetStrongPathsCount(gapAnalysis[key].paths))
                      .map((path) => GetResultLine(path, gapAnalysis, key))}
                    {Object.keys(gapAnalysis[key].paths).length > 3 && (
                      <Accordion>
                        <Accordion.Title
                          active={activeIndex === key}
                          index={key}
                          onClick={handleAccordionClick}
                        >
                          <Button>More Links (Total: {Object.keys(gapAnalysis[key].paths).length})</Button>
                        </Accordion.Title>
                        <Accordion.Content active={activeIndex === key}>
                          {Object.values<any>(gapAnalysis[key].paths)
                            .sort((a, b) => a.score - b.score)
                            .slice(
                              GetStrongPathsCount(gapAnalysis[key].paths),
                              Object.keys(gapAnalysis[key].paths).length
                            )
                            .map((path) => GetResultLine(path, gapAnalysis, key))}
                        </Accordion.Content>
                      </Accordion>
                    )}
                    {Object.keys(gapAnalysis[key].paths).length === 0 && <i>No links Found</i>}
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
