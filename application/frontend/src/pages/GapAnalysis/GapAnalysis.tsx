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

import { GapAnalysisPathStart } from '../../types';
import { getDocumentDisplayName } from '../../utils';

import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator';
import { useEnvironment } from '../../hooks';

const GetSegmentText = (segment, segmentID) => {
  let textPart = segment.end;
  let nextID = segment.end.id;
  let arrow = '->';
  if (segmentID !== segment.start.id) {
    textPart = segment.start;
    nextID = segment.start.id;
    arrow = '<-';
  }
  const text = `${arrow} ${segment.relationship} ${arrow} ${textPart.name} ${textPart.sectionID ?? ''} ${
    textPart.section ?? ''
  } ${textPart.subsection ?? ''} ${textPart.description ?? ''}`;
  return { text, nextID };
};

function useQuery() {
  const { search } = useLocation();

  return React.useMemo(() => new URLSearchParams(search), [search]);
}

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

  const GetStrength = (score) => {
    if (score < 5) return 'Strong';
    if (score > 20) return 'Weak';
    return 'Average';
  };

  const GetStrengthColor = (score) => {
    if (score < 5) return 'Green';
    if (score > 20) return 'Red';
    return 'Orange';
  };

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
        `${apiUrl}/gap_analysis?standard=${BaseStandard}&standard=${CompareStandard}`
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
    <div style={{ margin: '0 20px' }}>
      <Grid centered padded relaxed>
        <Grid.Row>
          <Grid.Column width={4}>
            <label>
              Base Sandard{' '}
              <Dropdown
                placeholder="Base Standard"
                search
                selection
                options={standardOptions}
                onChange={(e, { value }) => setBaseStandard(value?.toString())}
                value={BaseStandard}
              />
            </label>
          </Grid.Column>
          <Grid.Column width={4}>
            <label>
              Compare Sandard{' '}
              <Dropdown
                placeholder="Compare Standard"
                search
                selection
                options={standardOptions}
                onChange={(e, { value }) => setCompareStandard(value?.toString())}
                value={CompareStandard}
              />
            </label>
          </Grid.Column>
        </Grid.Row>
        {gapAnalysis && (
          <>
            <Grid.Column width={4} style={{ border: '1px solid black', margin: '2px' }}>
              <b>Generally: lower is better</b>
              <br />
              <b style={{ color: GetStrengthColor(0) }}>{GetStrength(0)}</b>: Closely connected likely to have
              majority overlap
              <br />
              <b style={{ color: GetStrengthColor(6) }}>{GetStrength(6)}</b>: Connected likely to have partial
              overlap
              <br />
              <b style={{ color: GetStrengthColor(22) }}>{GetStrength(22)}</b>: Weakly connected likely to
              have small or no overlap
              <br />
            </Grid.Column>
            <Grid.Column width={2} floated="right">
              <Button
                onClick={() => {
                  navigator.clipboard.writeText(
                    `${window.location.origin}/gap_analysis?base=${BaseStandard}&compare=${CompareStandard}`
                  );
                }}
                target="_blank"
              >
                <Icon name="share square" /> Share this anyalysis
              </Button>
            </Grid.Column>
          </>
        )}
      </Grid>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {gapAnalysis && (
        <Table celled padded compact style={{ margin: '5px' }}>
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>{BaseStandard}</Table.HeaderCell>
              <Table.HeaderCell>{CompareStandard}</Table.HeaderCell>
            </Table.Row>
          </Table.Header>

          <Table.Body>
            {Object.keys(gapAnalysis).map((key) => (
              <Table.Row key={key}>
                <Table.Cell>
                  <p>
                    <b>
                      {getDocumentDisplayName(gapAnalysis[key].start, true)}
                    </b>
                    <a
                      href={`/node/standard/${gapAnalysis[key].start.name}/section/${gapAnalysis[key].start.section}`}
                      target="_blank"
                    >
                      <Icon name="external" />
                    </a>
                  </p>
                </Table.Cell>
                <Table.Cell style={{ minWidth: '35vw' }}>
                  {Object.values<any>(gapAnalysis[key].paths)
                    .sort((a, b) => a.score - b.score)
                    .slice(0, 3)
                    .map((path) => {
                      let segmentID = gapAnalysis[key].start.id;
                      return (
                        <span key={path.end.id}>
                          <Popup
                            wide="very"
                            hoverable
                            content={path.path
                              .map((segment) => {
                                const { text, nextID } = GetSegmentText(segment, segmentID);
                                segmentID = nextID;
                                return text;
                              })
                              .join('')}
                            trigger={
                              <span>
                                {getDocumentDisplayName(path.end, true)} (
                                <b style={{ color: GetStrengthColor(path.score) }}>
                                  {GetStrength(path.score)}:{path.score}
                                </b>
                                ){' '}
                                <a
                                  href={`/node/standard/${path.end.name}/section/${path.end.section}`}
                                  target="_blank"
                                >
                                  <Icon name="external" />
                                </a>
                              </span>
                            }
                          />
                          <br />
                        </span>
                      );
                    })}
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
                          .slice(3, Object.keys(gapAnalysis[key].paths).length)
                          .map((path) => {
                            let segmentID = gapAnalysis[key].start.id;
                            return (
                              <span key={path.end.id}>
                                <Popup
                                  wide="very"
                                  hoverable
                                  content={path.path
                                    .map((segment) => {
                                      const { text, nextID } = GetSegmentText(segment, segmentID);
                                      segmentID = nextID;
                                      return text;
                                    })
                                    .join('')}
                                  trigger={
                                    <span>
                                      {getDocumentDisplayName(path.end, true)}
                                      <b style={{ color: GetStrengthColor(path.score) }}>
                                        {GetStrength(path.score)}:{path.score}
                                      </b>
                                      ){' '}
                                      <a
                                        href={`/node/standard/${path.end.name}/section/${path.end.section}`}
                                        target="_blank"
                                      >
                                        <Icon name="external" />
                                      </a>
                                    </span>
                                  }
                                />
                                <br />
                              </span>
                            );
                          })}
                      </Accordion.Content>
                    </Accordion>
                  )}
                  {Object.keys(gapAnalysis[key].paths).length === 0 && <i>No links Found</i>}
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
      )}
    </div>
  );
};
