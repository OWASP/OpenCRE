import React, { useEffect, useState } from 'react';
import { Accordion, Button, Dropdown, Grid, Popup, Table } from 'semantic-ui-react';
import { useLocation } from "react-router-dom";
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
  const text = `${arrow} ${segment.relationship} ${arrow} ${textPart.name} ${textPart.sectionID ?? ""} ${textPart.section ?? ""} ${textPart.subsection ?? ''} ${textPart.description ?? ''}`;
  return { text, nextID };
};

function useQuery() {
  const { search } = useLocation();

  return React.useMemo(() => new URLSearchParams(search), [search]);
}

export const GapAnalysis = () => {
  const standardOptions = [ // TODO: Automate this list
    { key: '', text: '', value: undefined },
    { key: 'OWASP Top 10 2021', text: 'OWASP Top 10 2021', value: 'OWASP Top 10 2021' },
    { key: 'NIST 800-53 v5', text: 'NIST 800-53 v5', value: 'NIST 800-53 v5' },
    { key: 'ISO 27001', text: 'ISO 27001', value: 'ISO 27001' },
    { key: 'Cloud Controls Matrix', text: 'Cloud Controls Matrix', value: 'Cloud Controls Matrix' },
    { key: 'ASVS', text: 'ASVS', value: 'ASVS' },
    { key: 'OWASP Proactive Controls', text: 'OWASP Proactive Controls', value: 'OWASP Proactive Controls' },
    { key: 'SAMM', text: 'SAMM', value: 'SAMM' },
    { key: 'CWE', text: 'CWE', value: 'CWE' },
    { key: 'OWASP Cheat Sheets', text: 'OWASP Cheat Sheets', value: 'OWASP Cheat Sheets' },
    {
      key: 'OWASP Web Security Testing Guide (WSTG)',
      text: 'OWASP Web Security Testing Guide (WSTG)',
      value: 'OWASP Web Security Testing Guide (WSTG)',
    },
    { key: 'NIST 800-63', text: 'NIST 800-63', value: 'NIST 800-63' },
    { key: 'Cheat_sheets', text: 'Cheat_sheets', value: 'Cheat_sheets' },
    { key: 'CAPEC', text: 'CAPEC', value: 'CAPEC' },
    { key: 'ZAP Rule', text: 'ZAP Rule', value: 'ZAP Rule' },
    { key: 'OWASP', text: 'OWASP', value: 'OWASP' },
    {
      key: 'OWASP Secure Headers Project',
      text: 'OWASP Secure Headers Project',
      value: 'OWASP Secure Headers Project',
    },
    { key: 'PCI DSS', text: 'PCI DSS', value: 'PCI DSS' },
    { key: 'OWASP Juice Shop', text: 'OWASP Juice Shop', value: 'OWASP Juice Shop' },
  ];
  const searchParams = useQuery();
  const [BaseStandard, setBaseStandard] = useState<string | undefined>(searchParams.get('base') ?? "");
  const [CompareStandard, setCompareStandard] = useState<string | undefined>(searchParams.get('compare') ?? "");
  const [gapAnalysis, setGapAnalysis] = useState<string>();
  const [activeIndex, SetActiveIndex] = useState<string>();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null | object>(null);
  const { apiUrl } = useEnvironment();

  const GetStrength = (score) => {
    if(score < 5) return 'Strong'
    if(score > 20) return 'Weak'
    return 'Average'
  } 
  useEffect(() => {
    const fetchData = async () => {
      const result = await fetch(
        `${apiUrl}/gap_analysis?standard=${BaseStandard}&standard=${CompareStandard}`
      );
      const resultObj = await result.json();
      setLoading(false);
      setGapAnalysis(resultObj);
    };

    if (!BaseStandard || !CompareStandard || BaseStandard === CompareStandard) return;
    setLoading(true);
    fetchData().catch(e => setError(e));
  }, [BaseStandard, CompareStandard, setGapAnalysis, setLoading, setError]);

  const handleAccordionClick = (e, titleProps) => {
    const { index } = titleProps;
    const newIndex = activeIndex === index ? -1 : index;
    SetActiveIndex(newIndex);
  };

  return (
    <div>
      <Grid centered padded relaxed>
        <Grid.Row>
          <Grid.Column width={4}>
            <Dropdown
              placeholder="Base Standard"
              search
              selection
              options={standardOptions}
              onChange={(e, { value }) => setBaseStandard(value?.toString())}
              value={BaseStandard}
            />
          </Grid.Column>
          <Grid.Column width={4}>
            <Dropdown
              placeholder="Compare Standard"
              search
              selection
              options={standardOptions}
              onChange={(e, { value }) => setCompareStandard(value?.toString())}
              value={CompareStandard}
            />
          </Grid.Column>
        </Grid.Row>
      </Grid>
      <LoadingAndErrorIndicator loading={loading} error={error} />
      {gapAnalysis && (
        <Table celled padded compact>
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>{BaseStandard}</Table.HeaderCell>
              <Table.HeaderCell>{CompareStandard}</Table.HeaderCell>
            </Table.Row>
          </Table.Header>

          <Table.Body>
            {Object.keys(gapAnalysis).map((key) => (
              <Table.Row key={key}>
                <Table.Cell >
                  <p>
                    <b>{gapAnalysis[key].start.name} {gapAnalysis[key].start.section} {gapAnalysis[key].start.subsection}</b><br />
                    {gapAnalysis[key].start.sectionID}
                    {gapAnalysis[key].start.description}
                  </p>
                </Table.Cell>
                <Table.Cell style={{ minWidth: '35vw' }}>
                  {gapAnalysis[key].paths
                    .sort((a, b) => a.score - b.score)
                    .slice(0, 3)
                    .map((path) => {
                      let segmentID = gapAnalysis[key].start.id;
                      return (
                        <span key={segmentID}>
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
                                {path.end.name} {path.end.sectionID} {path.end.section}{' '}
                                {path.end.subsection} {path.end.description} ({GetStrength(path.score)}:{path.score})
                              </span>
                            }
                          />
                          <br />
                        </span>
                      );
                    })}

                  <Accordion>
                    <Accordion.Title active={activeIndex === key} index={key} onClick={handleAccordionClick}>
                      <Button>Weakerlinks (Total Links: {gapAnalysis[key].paths.length})</Button>
                    </Accordion.Title>
                    <Accordion.Content active={activeIndex === key}>
                      Weaker Links: <br />
                      {gapAnalysis[key].paths
                        .sort((a, b) => a.score - b.score)
                        .slice(2, gapAnalysis[key].paths.length)
                        .map((path) => {
                          let segmentID = gapAnalysis[key].start.id;
                          return (
                            <span key={segmentID}>
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
                                    {path.end.name} {path.end.sectionID} {path.end.section}{' '}
                                    {path.end.subsection} {path.end.description} {GetStrength(path.score)}:{path.score})
                                  </span>
                                }
                              />
                              <br />
                            </span>
                          );
                        })}
                    </Accordion.Content>
                  </Accordion>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
      )}
    </div>
  );
};
