import './BodyText.scss';

import React, { useState } from 'react';

export const SearchBody = () => {
  return (
    <div className="index-text">
      <h1>OpenCRE</h1>
      <p>
        <b>
          OpenCRE is an interactive content linking platform for uniting security standards and guidelines
          into one overview. It offers easy and robust access to relevant information when designing,
          developing, testing, procuring and organising secure software.
        </b>
      </p>
      <p>
        <b>
          Use the search bar or <a href="/root_cres">browse the catalogue of all top-level topics</a>, try
          <a href="/node/standard/OWASP%20Top%2010%202021"> the Top10 2021 page</a> and click around, or{' '}
          <a href="/search/session">search for "Session"</a>, or check out{' '}
          <a href="/cre/764-507"> CRE 764-507 </a> or <a href="/cre/581-525">CRE 581-525</a> to access a wide
          array of relevant details. This includes criteria in several standards, testing advice, development
          tips, in-depth technical information, threat descriptions, articles, tool settings, and related
          topics.
        </b>
      </p>
      <h3>Do you have an OWASP account? Try talking to our <a href='/chatbot'>CRE Chatbot</a></h3>
      <h2>HOW?</h2>
      <p>
        OpenCRE links each section of a resource (like a standard or guideline) to a shared topic, known as a
        Common Requirement, causing that section to also link with all other resources that link to the same
        topic. This 1) enables users to find all combined information from relevant sources, 2) it facilitates
        a shared and better understanding of cyber security, and 3) it allows standard makers to have links
        that keep working and offer all the information that readers need, alleviating their need to cover
        everything themselves. OpenCRE maintains itself: links to OpenCRE in the standard text are scanned
        automatically. Furthermore, topics are linked with related other topics, creating a semantic web for
        security to explore.
      </p>
      <p>
        An easy way to link to OpenCRE topics, is to use a familiar standard. For example, using CWE to link
        to OpenCRE content on the topic of XXE injection:
        <a href="/smartlink/standard/CWE/611">www.opencre.org/smartlink/standard/CWE/611</a>.
      </p>
      <h2>WHO?</h2>
      <p>
        It's the brainchild of independent software security professionals such as Spyros Gasteratos and Rob
        van der Veer, who joined forces to tackle the complexities and segmentation in current security
        standards and guidelines. They collaborated closely with the SKF, OpenSSF and the Owasp Top 10
        project. OpenCRE is an open-source platform overseen by the OWASP foundation through the
        <a href="https://owasp.org/www-project-integration-standards/"> OWASP Integration standard project</a>
        . The goal is to foster better coordination among security initiatives.
      </p>
      <p>
        OpenCRE currently links OWASP standards (Top 10, ASVS, Proactive Controls, Cheat sheets, Testing
        guide, ZAP, SAMM), plus several other sources (CWE, CAPEC, NIST-800 53, NIST-800 63b, Cloud Control
        Matrix, ISO27001, ISO27002, NIST SSDF, and PCI-DSS).
      </p>
      <p>
        Contact us via (rob.vanderveer [at] owasp.org) to join the movement. Currently, a stakeholder group is
        being formed.
      </p>
      <p>
        For more details, see this
        <a href="https://www.youtube.com/watch?v=7knF14t0Svg"> presentation video</a>, read the
        <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/CRE-Explained6.pdf">
          {' '}
          CRE explanation document{' '}
        </a>{' '}
        or click the diagram below.
      </p>

      <a href="/opencregraphic2.png" target="_blank">
        <img className="align-middle mx-auto " src="/tn_opencregraphic2.jpg" alt="Diagram" />
      </a>
    </div>
  );
};
