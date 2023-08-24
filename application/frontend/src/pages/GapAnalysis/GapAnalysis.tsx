import React, { useEffect, useState } from 'react';
import { Accordion, Dropdown, Icon, Label, Popup, Segment, Table } from 'semantic-ui-react';

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
  const text = `${arrow} ${segment.relationship} ${arrow} ${textPart.name} ${textPart.sectionID} ${textPart.section} ${textPart.subsection} ${textPart.description}`;
  return { text, nextID };
};

export const GapAnalysis = () => {
  const standardOptions = [
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
  const [BaseStandard, setBaseStandard] = useState<string>();
  const [CompareStandard, setCompareStandard] = useState<string>();
  const [gapAnalysis, setGapAnalysis] = useState<string>();
  const [activeIndex, SetActiveIndex] = useState<string>();
  const { apiUrl } = useEnvironment();
  useEffect(() => {
    const fetchData = async () => {
      const result = await fetch(
        `${apiUrl}/gap_analysis?standard=${BaseStandard}&standard=${CompareStandard}`
      );
      const resultObj = await result.json();
      setGapAnalysis(resultObj);
    };

    if (!BaseStandard || !CompareStandard || BaseStandard === CompareStandard) return;
    fetchData().catch(console.error);
  }, [BaseStandard, CompareStandard, setGapAnalysis]);

  const handleAccordionClick = (e, titleProps) => {
    const { index } = titleProps;
    const newIndex = activeIndex === index ? -1 : index;
    SetActiveIndex(newIndex);
  };

  return (
    <div>
      <Dropdown
        placeholder="Base Standard"
        search
        selection
        options={standardOptions}
        onChange={(e, { value }) => setBaseStandard(value?.toString())}
      />
      <Dropdown
        placeholder="Compare Standard"
        search
        selection
        options={standardOptions}
        onChange={(e, { value }) => setCompareStandard(value?.toString())}
      />
      {gapAnalysis && (
        <Table celled padded>
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>{BaseStandard}</Table.HeaderCell>
              <Table.HeaderCell>{CompareStandard}</Table.HeaderCell>
            </Table.Row>
          </Table.Header>

          <Table.Body>
            {Object.keys(gapAnalysis).map((key) => (
              <Table.Row>
                <Table.Cell>
                  <Label ribbon>
                    {gapAnalysis[key].start.name} {gapAnalysis[key].start.sectionID}{' '}
                    {gapAnalysis[key].start.section} {gapAnalysis[key].start.subsection}{' '}
                    {gapAnalysis[key].start.description} {gapAnalysis[key].start.id}
                  </Label>
                </Table.Cell>
                <Table.Cell>
                  <Accordion>
                    <Accordion.Title active={activeIndex === key} index={key} onClick={handleAccordionClick}>
                      <Icon name="dropdown" />
                      {gapAnalysis[key].paths
                        .sort((a, b) => a.score - b.score)
                        .slice(0, 3)
                        .map((path) => {
                          let segmentID = gapAnalysis[key].start.id;
                          return (
                            <>
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
                                    {path.end.subsection} {path.end.description} ({path.score})
                                  </span>
                                }
                              />
                              <br />
                            </>
                          );
                        })}
                      (Total Links: {gapAnalysis[key].paths.length})
                    </Accordion.Title>
                    <Accordion.Content active={activeIndex === key}>
                      {gapAnalysis[key].paths
                        .sort((a, b) => a.score - b.score)
                        .slice(2, gapAnalysis[key].paths.length)
                        .map((path) => {
                          let segmentID = gapAnalysis[key].start.id;
                          return (
                            <>
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
                                    {path.end.subsection} {path.end.description} ({path.score})
                                  </span>
                                }
                              />
                              <br />
                            </>
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
