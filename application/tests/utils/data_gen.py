from application.defs import cre_defs as defs


def root_csv_data():
    input_data = [
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "",
            "Standard Top 10 2017 item": "A2_Broken_Authentication",
            "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
            "CRE ID": "",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST 800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "tag-connection",
            "Standard Top 10 2017 item": "",
            "Standard Top 10 2017 Hyperlink": "",
            "CRE ID": "123-123",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST 800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "Authentication",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "",
            "Standard Top 10 2017 item": "A2_Broken_Authentication",
            "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
            "CRE ID": "888-888",
            "Standard CWE (from ASVS)": "19876",
            "Standard CWE (from ASVS)-hyperlink": "https://example.com/cwe19876",
            "Link to other CRE": "FooBar",
            "Standard NIST 800-53 v5": "SA-22 Unsupported System Components",
            "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5",
            "Standard NIST-800-63 (from ASVS)": "4444/3333",
            "Standard OPC (ASVS source)": "123-123654",
            "Standard OPC (ASVS source)-hyperlink": "https://example.com/opc",
            "CRE Tags": "tag-connection",
            "Standard WSTG-item": "2.1.2.3",
            "Standard WSTG-Hyperlink": "https://example.com/wstg",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "Authentication",
            "CRE hierarchy 2": "Authentication mechanism",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "",
            "Standard Top 10 2017 item": "See higher level topic",
            "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
            "CRE ID": "333-333",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "https://example.com/nist-800-53-v5",
            "Standard NIST-800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "123-123654",
            "Standard OPC (ASVS source)-hyperlink": "https://example.com/opc",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
        {
            "Standard ASVS 4.0.3 Item": "V1.2.3",
            "Standard ASVS 4.0.3 description": 10,
            "Standard ASVS 4.0.3 Hyperlink": "https://example.com/asvs",
            "ASVS-L1": "",
            "ASVS-L2": "X",
            "ASVS-L3": "X",
            "CRE hierarchy 1": "Authentication",
            "CRE hierarchy 2": "Authentication mechanism",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "Verify that the application uses a single vetted authentication mechanism",
            "Standard Top 10 2017 item": "See higher level topic",
            "Standard Top 10 2017 Hyperlink": "https://example.com/top102017",
            "CRE ID": "444-444",
            "Standard CWE (from ASVS)": 306,
            "Standard CWE (from ASVS)-hyperlink": "https://example.com/cwe306",
            "Link to other CRE": "Logging and Error handling",
            "Standard NIST 800-53 v5": (
                "PL-8 Information Security Architecture\n"
                "SC-39 PROCESS ISOLATION\n"
                "SC-3 SECURITY FUNCTION"
            ),
            "Standard NIST 800-53 v5-hyperlink": (
                "https://example.com/nist-800-53-v5\n"
                "https://example.com/nist-800-53-v5\n"
                "https://example.com/nist-800-53-v5"
            ),
            "Standard NIST-800-63 (from ASVS)": "None",
            "Standard OPC (ASVS source)": "123-123654;123-123653",
            "Standard OPC (ASVS source)-hyperlink": "https://example.com/opc;https://example.com/opc",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "FooParent",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "",
            "Standard Top 10 2017 item": "",
            "Standard Top 10 2017 Hyperlink": "",
            "CRE ID": "168-176",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST-800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "FooParent",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "FooBar",
            "Standard Top 10 2017 item": "",
            "Standard Top 10 2017 Hyperlink": "",
            "CRE ID": "999-999",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "Authentication mechanism",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST-800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "foo; bar",
            "Standard Cheat_sheets-Hyperlink": "https://example.com/cheatsheetf/foo; https://example.com/cheatsheetb/bar",
        },
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "Logging and Error handling",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "",
            "Standard Top 10 2017 item": "",
            "Standard Top 10 2017 Hyperlink": "",
            "CRE ID": "543-543",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST-800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
    ]
    # register cres
    cre_123 = defs.CRE(id="123-123", name="tag-connection")
    cre_8 = defs.CRE(id="888-888", name="Authentication", tags=["tag-connection"])
    cre_3 = defs.CRE(id="333-333", name="Authentication mechanism")
    cre_4 = defs.CRE(
        id="444-444",
        name="Verify that the application uses a single vetted authentication mechanism",
    )
    cre_logging = defs.CRE(id="543-543", name="Logging and Error handling")
    cre_fooParent = defs.CRE(id="168-176", name="FooParent")
    cre_9 = defs.CRE(id="999-999", name="FooBar")

    # register standards
    s_top10_2017_a2 = defs.Standard(
        hyperlink="https://example.com/top102017",
        name="OWASP Top 10 2017",
        section="A2_Broken_Authentication",
    )
    s_opc_123 = defs.Standard(
        name="OWASP Proactive Controls",
        section="123-123654",
        hyperlink="https://example.com/opc",
    )
    s_opc_653 = defs.Standard(
        name="OWASP Proactive Controls",
        section="123-123653",
        hyperlink="https://example.com/opc",
    )
    s_cwe_19876 = defs.Standard(
        name="CWE", sectionID="19876", hyperlink="https://example.com/cwe19876"
    )
    s_cwe_306 = defs.Standard(
        name="CWE", sectionID="306", hyperlink="https://example.com/cwe306"
    )
    s_wstg_2123 = defs.Standard(
        name="OWASP Web Security Testing Guide (WSTG)",
        section="2.1.2.3",
        hyperlink="https://example.com/wstg",
    )
    s_asvs_10 = defs.Standard(
        name="ASVS",
        section="10",
        sectionID="V1.2.3",
        hyperlink="https://example.com/asvs",
    )
    s_cheatsheet_f = defs.Standard(
        name="OWASP Cheat Sheets",
        section="foo",
        hyperlink="https://example.com/cheatsheetf/foo",
    )
    s_cheatsheet_b = defs.Standard(
        name="OWASP Cheat Sheets",
        section="bar",
        hyperlink="https://example.com/cheatsheetb/bar",
    )
    s_nist_63_4 = defs.Standard(name="NIST 800-63", section="4444")
    s_nist_63_3 = defs.Standard(name="NIST 800-63", section="3333")
    s_nist_53_sa22 = defs.Standard(
        name="NIST 800-53 v5",
        section="SA-22 Unsupported System Components",
        hyperlink="https://example.com/nist-800-53-v5",
    )
    s_nist_53_pl8 = defs.Standard(
        name="NIST 800-53 v5",
        section="PL-8 Information Security Architecture",
        hyperlink="https://example.com/nist-800-53-v5",
    )
    s_nist_53_sc39 = defs.Standard(
        name="NIST 800-53 v5",
        section="SC-39 PROCESS ISOLATION",
        hyperlink="https://example.com/nist-800-53-v5",
    )
    s_nist_53_sc3 = defs.Standard(
        name="NIST 800-53 v5",
        section="SC-3 SECURITY FUNCTION",
        hyperlink="https://example.com/nist-800-53-v5",
    )

    # cre links AKA semantic graph structure
    cre_9.add_link(
        defs.Link(ltype=defs.LinkTypes.Related, document=cre_3.shallow_copy())
    )
    cre_fooParent.add_link(
        defs.Link(ltype=defs.LinkTypes.Contains, document=cre_9.shallow_copy())
    )

    cre_8.add_link(
        defs.Link(ltype=defs.LinkTypes.Related, document=cre_9.shallow_copy())
    ).add_link(
        defs.Link(ltype=defs.LinkTypes.Contains, document=cre_3.shallow_copy())
    ).add_link(
        defs.Link(ltype=defs.LinkTypes.Related, document=cre_123.shallow_copy())
    )
    cre_3.add_link(
        defs.Link(ltype=defs.LinkTypes.Contains, document=cre_4.shallow_copy())
    )
    cre_4.add_link(
        defs.Link(ltype=defs.LinkTypes.Related, document=cre_logging.shallow_copy())
    )
    # standard links AKA semantic web content
    s_cheatsheet_b.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_9.shallow_copy())
    )
    s_cheatsheet_f.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_9.shallow_copy())
    )
    s_top10_2017_a2.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_8.shallow_copy())
    )
    s_nist_63_3.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_8.shallow_copy())
    )
    s_nist_63_4.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_8.shallow_copy())
    )
    s_wstg_2123.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_8.shallow_copy())
    )
    s_cwe_19876.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_8.shallow_copy())
    )
    s_opc_123.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_8.shallow_copy())
    ).add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_3.shallow_copy())
    ).add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_4.shallow_copy())
    )
    s_opc_653.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_4.shallow_copy())
    )
    s_nist_53_sa22.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_8.shallow_copy())
    )
    s_asvs_10.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_4.shallow_copy())
    )
    s_cwe_306.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_4.shallow_copy())
    )

    s_nist_53_pl8.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_4.shallow_copy())
    )
    s_nist_53_sc39.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_4.shallow_copy())
    )
    s_nist_53_sc3.add_link(
        defs.Link(ltype=defs.LinkTypes.LinkedTo, document=cre_4.shallow_copy())
    )

    expected = {
        defs.Credoctypes.CRE.value: [
            cre_123,
            cre_8,
            cre_3,
            cre_4,
            cre_logging,
            cre_fooParent,
            cre_9,
        ],
        "NIST 800-53 v5": [
            s_nist_53_pl8,
            s_nist_53_sa22,
            s_nist_53_sc39,
            s_nist_53_sc3,
        ],
        "NIST 800-63": [s_nist_63_3, s_nist_63_4],
        "OWASP Cheat Sheets": [s_cheatsheet_b, s_cheatsheet_f],
        "OWASP Top 10 2017": [s_top10_2017_a2],
        "OWASP Proactive Controls": [s_opc_123, s_opc_653],
        "CWE": [s_cwe_19876, s_cwe_306],
        "OWASP Web Security Testing Guide (WSTG)": [s_wstg_2123],
        "ASVS": [s_asvs_10],
    }
    return input_data, expected


def root_csv_cre_only():
    input_data = [
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "FooBar",
            "Standard Top 10 2017 item": "",
            "Standard Top 10 2017 Hyperlink": "",
            "CRE ID": "999-999",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "Authentication mechanism",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST-800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "Authentication mechanism",
            "Standard Top 10 2017 item": "",
            "Standard Top 10 2017 Hyperlink": "",
            "CRE ID": "992-992",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST-800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "",
            "Standard Cheat_sheets-Hyperlink": "",
        },
    ]
    cre9 = defs.CRE(name="FooBar", id="999-999")
    cre8 = defs.CRE(name="Authentication Mechanism", id="992-992")
    expected = {defs.Credoctypes.CRE.value: [cre9, cre8]}
    return input_data, expected


def root_csv_minimum_data():
    input_data = [
        {
            "Standard ASVS 4.0.3 Item": "",
            "Standard ASVS 4.0.3 description": "",
            "Standard ASVS 4.0.3 Hyperlink": "",
            "ASVS-L1": "",
            "ASVS-L2": "",
            "ASVS-L3": "",
            "CRE hierarchy 1": "",
            "CRE hierarchy 2": "",
            "CRE hierarchy 3": "",
            "CRE hierarchy 4": "FooBar",
            "Standard Top 10 2017 item": "",
            "Standard Top 10 2017 Hyperlink": "",
            "CRE ID": "999-999",
            "Standard CWE (from ASVS)": "",
            "Standard CWE (from ASVS)-hyperlink": "",
            "Link to other CRE": "Authentication mechanism",
            "Standard NIST 800-53 v5": "",
            "Standard NIST 800-53 v5-hyperlink": "",
            "Standard NIST-800-63 (from ASVS)": "",
            "Standard OPC (ASVS source)": "",
            "Standard OPC (ASVS source)-hyperlink": "",
            "CRE Tags": "",
            "Standard WSTG-item": "",
            "Standard WSTG-Hyperlink": "",
            "Standard Cheat_sheets": "foo; bar",
            "Standard Cheat_sheets-Hyperlink": "https://example.com/cheatsheetf/foo; https://example.com/cheatsheetb/bar",
        },
    ]
    return input_data


def export_format_data():
    input_data = [
        {
            "CRE 0": "000-001|C0",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "SE1 description",
            "S1|hyperlink": "https://example.com/S1",
            "S1|id": "id1",
            "S1|name": "SE1",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "",
            "CRE 1": "222-222|C2",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "",
            "CRE 1": "",
            "CRE 2": "333-333|C3",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "SE3",
            "S3|hyperlink": "https://example.com/S3",
            "S3|id": "5.3",
            "S3|name": "SE3",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "",
            "CRE 1": "",
            "CRE 2": "333-333|C3",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "SE3 double",
            "S3|hyperlink": "https://example.com/S3.4",
            "S3|id": "5.3.4",
            "S3|name": "SE3.4",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "444-444|C4",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "SE1 description",
            "S1|hyperlink": "https://example.com/S1",
            "S1|id": "id1",
            "S1|name": "SE1",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "555-555|C5",
            "CRE 5": "",
            "S1|description": "SE1 description",
            "S1|hyperlink": "https://example.com/S1",
            "S1|id": "id1",
            "S1|name": "SE1",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "666-666|C6",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "777-777|C7",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "888-888|C8",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "https://example.com/SL",
            "SL|id": "slid",
            "SL|name": "SSL",
        },
        {
            "CRE 0": "",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "https://example.com/SL2",
            "SL2|id": "sl2id",
            "SL2|name": "SSL2",
            "SLL|hyperlink": "",
            "SLL|id": "",
            "SLL|name": "",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
        {
            "CRE 0": "",
            "CRE 1": "",
            "CRE 2": "",
            "CRE 3": "",
            "CRE 4": "",
            "CRE 5": "",
            "S1|description": "",
            "S1|hyperlink": "",
            "S1|id": "",
            "S1|name": "",
            "S2|description": "",
            "S2|hyperlink": "",
            "S2|id": "",
            "S2|name": "",
            "S3|description": "",
            "S3|hyperlink": "",
            "S3|id": "",
            "S3|name": "",
            "S4|description": "",
            "S4|hyperlink": "",
            "S4|id": "",
            "S4|name": "",
            "S5|description": "",
            "S5|hyperlink": "",
            "S5|id": "",
            "S5|name": "",
            "SL2|hyperlink": "",
            "SL2|id": "",
            "SL2|name": "",
            "SLL|hyperlink": "https://example.com/SLL",
            "SLL|id": "SBESLL",
            "SLL|name": "SSLL",
            "SL|hyperlink": "",
            "SL|id": "",
            "SL|name": "",
        },
    ]

    expected = {
        defs.Credoctypes.CRE.value: [
            defs.CRE(
                id="000-001",
                name="C0",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S1",
                            section="SE1",
                            sectionID="id1",
                            hyperlink="https://example.com/S1",
                            description="SE1 description",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(
                            id="222-222",
                            name="C2",
                        ),
                    ),
                ],
            ),
            defs.CRE(
                id="222-222",
                name="C2",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(id="333-333", name="C3"),
                    )
                ],
            ),
            defs.CRE(
                id="333-333",
                name="C3",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S3",
                            section="SE3",
                            sectionID="5.3",
                            hyperlink="https://example.com/S3",
                            description="SE3",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S3",
                            section="SE3.4",
                            sectionID="5.3.4",
                            hyperlink="https://example.com/S3.4",
                            description="SE3 double",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(id="444-444", name="C4"),
                    ),
                ],
            ),
            defs.CRE(
                id="444-444",
                name="C4",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S1",
                            section="SE1",
                            sectionID="id1",
                            description="SE1 description",
                            hyperlink="https://example.com/S1",
                        ),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.Contains,
                        document=defs.CRE(id="555-555", name="C5"),
                    ),
                ],
            ),
            defs.CRE(
                id="555-555",
                name="C5",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.Standard(
                            name="S1",
                            section="SE1",
                            sectionID="id1",
                            description="SE1 description",
                            hyperlink="https://example.com/S1",
                        ),
                    ),
                ],
            ),
            defs.CRE(
                id="666-666",
                name="C6",
            ),
            defs.CRE(
                id="777-777",
                name="C7",
            ),
            defs.CRE(
                id="888-888",
                name="C8",
            ),
        ],
        "S1": [
            defs.Standard(
                name="S1",
                section="SE1",
                description="SE1 description",
                sectionID="id1",
                hyperlink="https://example.com/S1",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(id="000-001", name="C0"),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(id="444-444", name="C4"),
                    ),
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(id="555-555", name="C5"),
                    ),
                ],
            )
        ],
        "S3": [
            defs.Standard(
                name="S3",
                section="SE3",
                description="SE3",
                sectionID="5.3",
                hyperlink="https://example.com/S3",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(id="333-333", name="C3"),
                    ),
                ],
            ),
            defs.Standard(
                name="S3",
                section="SE3.4",
                description="SE3 double",
                sectionID="5.3.4",
                hyperlink="https://example.com/S3.4",
                links=[
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=defs.CRE(id="333-333", name="C3"),
                    ),
                ],
            ),
        ],
        "SL": [
            defs.Standard(
                name="SL",
                section="SSL",
                description="",
                sectionID="slid",
                hyperlink="https://example.com/SL",
            )
        ],
        "SL2": [
            defs.Standard(
                name="SL2",
                section="SSL2",
                sectionID="sl2id",
                hyperlink="https://example.com/SL2",
            )
        ],
        "SLL": [
            defs.Standard(
                name="SLL",
                description="",
                section="SSLL",
                hyperlink="https://example.com/SLL",
                sectionID="SBESLL",
            )
        ],
    }
    return input_data, expected
