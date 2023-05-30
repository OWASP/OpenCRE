import './BodyText.scss';

import React, { useState } from 'react';

export const SearchBody = () => {
  return (
    <div className="index-text">
      <h1>OpenCRE</h1>
      <p>
        <b>OpenCRE is an interactive content linking platform for uniting security standards and guidelines. It
        offers easy and robust access to relevant information when designing, developing, testing, procuring 
        and organising secure software.</b>
      </p>
      <p>
        <b>Use the search bar or <a href="/root_cres">browse the overview of all top-level topics</a>, try 
        <a href="/node/standard/Top10%202017/">the Top10 2017 page</a> and click around, or 
        <a href="/search/session">search for "Session"</a>, or look at 
        <a href="/cre/764-507"> CRE 764-507 </a> to see the wealth of information: relevant criteria in several
        standards, testing guidance, development tips, more technical detail, threat descriptions, 
        articles, tool configurations, related topics etc.</b>
      </p>
      <h2>HOW?</h2>
      <p>
        OpenCRE links each section of a resource (eg. a standard or guideline) to a shared topic (a Common Requirement),
        causing that section to also link with all other resources that link to the same topic. This 1) enables users to
        find all combined information from relevant sources, 2) it facilitates a shared and better
        understanding of cyber security, and 3) it allows standard makers to have links that keep working and
        offer all the information that readers need, so they don’t have to cover it all themselves. The CRE
        maintains itself: links to OpenCRE in the standard text are scanned automatically. Furthermore, topics are
        linked with related other topics, creating a semantic web for security to explore.
      </p>
      <p>
        An easy way to link to OpenCRE topics, is to use a familiar standard. For example, using 
        CWE to link to OpenCRE content on the topic of XXE injection: <a href"/smartlink/standard/CWE/611">
        www.opencre.org/smartlink/standard/CWE/611</a>.
      </p>
      <h2>WHO?</h2>
      <p>
        Independent software security professionals got together to find a solution for the complexity and
        fragmentation in today’s landscape of security standards and guidelines. These people are Spyros
        Gasteratos, Rob van der Veer with many friends, in close collaboration with the SKF, OpenSSF and
        Owasp Top 10 project. OpenCRE is completely open source and governed by the OWASP foundation in the
        <a href="https://owasp.org/www-project-integration-standards/"> OWASP Integration standard project</a>, 
        as part of the strategy to create more alignment between security initiatives.
      </p>
      <p>
        OpenCRE currently links OWASP standards (Top 10, ASVS, Proactive Controls, Cheat
        sheets, Testing guide, ZAP), plus several other sources (CWE, CAPEC, NIST-800 53, NIST-800 63b, Cloud Control 
        Matrix, ISO27001, ISO27002 and PCI-DSS).
      </p>
      <p>
        Contact us via (rob.vanderveer [at] owasp.org) to join the movement. Currently, a stakeholder group is
        being formed.
      </p>
      <p>
        For more details, see this
        <a href="https://www.youtube.com/watch?v=7knF14t0Svg"> presentation video</a>, or read the
        <a href="https://github.com/OWASP/www-project-integration-standards/raw/master/writeups/CRE-Explained6.pdf">
          {' '}
          CRE explanation document
        </a>
        .
      </p>


    </div>
  );
};
