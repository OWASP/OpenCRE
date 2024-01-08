import './BodyText.scss';

import React, { useState } from 'react';

export const SearchBody = () => {
  return (
    <div className="index-text">
      <h1>OpenCRE</h1>
      <p>
        <strong>
          OpenCRE is the interactive content linking platform for uniting security standards and guidelines
          into one overview. It offers easy and robust access to relevant information when designing,
          developing, testing, procuring and organising secure software.
        </strong>
      </p>
      <p>
        <strong>
          Use the search bar or <a href="/root_cres">browse the catalogue of all top-level topics</a>, try
          <a href="/node/standard/OWASP%20Top%2010%202021"> the Top10 2021 page</a> and click around, or{' '}
          <a href="/search/session">search for "Session"</a>, or check out{' '}
          <a href="/cre/764-507"> CRE 764-507 </a> or <a href="/cre/581-525">CRE 581-525</a> to see the{' '}
          <b>Multilink</b>
          feature: one link to OpenCRE gives access to a wide range of standards and related topics: testing
          advice, development, in-depth technical information, threat descriptions, articles, and tool
          settings.
        </strong>
      </p>
      <p>
        <strong>
          Use <a href="/chatbot">OpenCRE Chat</a> to ask any security question (Google account required to
          maximize queries per minute). In collaboration with Google, we injected all the standards in OpenCRE
          into an AI model to create the world's first security-specialized chatbot. This ensures you get a
          more reliable answer, and also a reference to a reputable source.
        </strong>
      </p>
      <p>
        <strong>
          Use <a href="/map_analysis">Map Analysis</a> to find how any two standards connect with eachother
        </strong>
      </p>
      <h2>HOW?</h2>
      <p>
        OpenCRE links each section of a resource (like a standard or guideline) to a shared topic, known as a
        Common Requirement, causing that section to also link with all other resources that link to the same
        topic. This 1) enables users to find all combined information from relevant sources, 2) facilitates a
        shared and better understanding of cyber security, and 3) allows standard makers to have links that
        keep working and offer all the information that readers need, alleviating their need to cover
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
        OpenCRE is the brainchild of software security professionals Spyros Gasteratos and Rob van der Veer,
        who joined forces to tackle the complexities and segmentation in current security standards and
        guidelines. They collaborated closely with many initiatives, including SKF, OpenSSF and the Owasp Top
        10 project. OpenCRE is an open-source platform overseen by the OWASP foundation through the
        <a href="https://owasp.org/www-project-integration-standards/"> OWASP Integration standard project</a>
        . The goal is to foster better coordination among security initiatives.
      </p>
      <p>
        OpenCRE currently links OWASP standards (Top 10, ASVS, Proactive Controls, Cheat sheets, Testing
        guide, ZAP, Juice shop, SAMM), plus several other sources (CWE, CAPEC, NIST-800 53, NIST-800 63b,
        Cloud Control Matrix, ISO27001, ISO27002, and NIST SSDF).
      </p>
      <p>
        Contact us via (rob.vanderveer [at] owasp.org) for any questions, remarks or to join the movement.
        Currently, a stakeholder group is being formed.
      </p>
      <p>
        For more details, see this
        <a href="https://www.youtube.com/watch?v=TwNroVARmB0"> interview and demo video</a>, read the
        <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/opencredcslides.pdf">
          {' '}
          OpenCRE slides from the 2023 Appsec conference in Washington DC{' '}
        </a>
        , follow our
        <a href="https://www.linkedin.com/company/96695329"> LinkedIn page </a>, click the diagram below, or{' '}
        <a href="https://zeljkoobrenovic.github.io/opencre-explorer/">
          browse our catalogue textually or graphically
        </a>
        .
      </p>

      <a href="/opencregraphic2.png" target="_blank">
        <img className="align-middle mx-auto " src="/tn_opencregraphic2.jpg" alt="Diagram" />
      </a>
    </div>
  );
};
