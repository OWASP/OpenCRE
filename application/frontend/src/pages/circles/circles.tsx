import { useQuery } from 'react-query';
import './circles.scss';
import {select,scaleLinear,interpolateHcl,pack,hierarchy,event,transition,interpolateZoom} from 'd3'
import { useEnvironment } from '../../hooks';
import React, { useContext, useEffect, useMemo, useState } from 'react';
import { Document, LinkedDocument } from '../../types';
import { TYPE_CONTAINS } from '../../const';

const RenderCircle = () => {
    const { apiUrl } = useEnvironment();
    const [rootCREs, setRootCREs] = useState<Document[]>()
    const [data, setData] = useState<Document[]>()

    useQuery<{ data: Document }, string>(
        'root_cres',
        () =>
            fetch(`${apiUrl}/root_cres`)
                .then((res) => res.json())
                .then((resjson) => {
                    setRootCREs(resjson.data);
                    return resjson;
                }),
        {
            retry: false,
            enabled: false,
            onSettled: () => {
            },
        }
    );
    const docs = localStorage.getItem("documents")
    useEffect(() => {
        if (docs != null) {
            setData(JSON.parse(docs).sort((a, b) => (a.id + '').localeCompare(b.id + '')));
        }
    }, [docs])

    const query = useQuery(
        'everything',
        () => {
            if (docs == null) {
                fetch(`${apiUrl}/everything`)
                    .then((res) => { return res.json() })
                    .then((resjson) => {
                        return resjson.data
                    }).then((data) => {
                        if (data) {
                            localStorage.setItem("documents", JSON.stringify(data));
                            setData(data)
                        }
                    }),
                {
                    retry: false,
                    enabled: false,
                    onSettled: () => {
                    },
                }
            }

        }
    );

    var svg = select("svg"),
        margin = 20,
        diameter = +svg.attr("width"),
        g = svg.append("g").attr("transform", "translate(" + diameter / 2 + "," + diameter / 2 + ")");

    var color = scaleLinear()
        .domain([-1, 5])
        .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"])
        .interpolate(interpolateHcl);

    var pack = pack()
        .size([diameter - margin, diameter - margin])
        .padding(2);


    // data?.forEach(dat => {
    //     dat.links = [];
    // })
    interface circleDoc extends Document {
        size: number
    }
    function getById(id) {
        let x = data?.filter(i => i.id === id)[0]
        if (x) {
            let y: Partial<circleDoc> = x
            y.size = 0
            return y
        }
    }

    function populateChildren(id) {
        const cre = getById(id);
        if (cre)
            cre.links?.filter(link => link.ltype === TYPE_CONTAINS).forEach(link => {
                let child: any = getById(link.document.id);
                if (child) { cre.links?.push({ document: child, ltype: TYPE_CONTAINS }) }
                populateChildren(link.document.id);
                if (child?.links?.length === 0) {
                    child.size = 1;
                }
            });
    }

    rootCREs?.forEach(node => populateChildren(node?.id));

    let root: any = {
        "name": "cluster",
        "children": rootCREs
    }

    root = hierarchy(root)
        .sum(function (d) {
            return d.size;
        })
        .sort(function (a, b) {
            return b.value - a.value;
        });

    var focus = root,
        nodes = pack(root).descendants(),
        view;

    var circle = g.selectAll("circle")
        .data(nodes)
        .enter().append("circle")
        .attr("class", function (d) {
            return d.parent ? d.children ? "node" : "node node--leaf" : "node node--root";
        })
        .style("fill", function (d) {
            return d.children ? color(d.depth) : (d.data.color ? d.data.color : null);
        })
        .on("click", function (d) {
            if (focus !== d) zoom(d), event.stopPropagation();
        });

    var text = g.selectAll("text")
        .data(nodes)
        .enter().append("text")
        .attr("class", "label")
        .style("fill-opacity", function (d) {
            return d.parent === root ? 1 : 0;
        })
        .style("display", function (d) {
            return d.parent === root ? "inline" : "none";
        })
        .text(function (d) {
            let name = d.data.name.length > 33 ? (d.data.name.substr(0, 14) + "..." + d.data.name.substr(d.data.name.length - 14)) : d.data.name;
            if (d.data.children && d.data.children.length > 0) name += ' (' + d.data.children.length + ')'
            return name;
        });

    var node = g.selectAll("circle,text");

    svg
        .style("background", color(-1))
        .on("click", function () {
            zoom(root);
        });

    zoomTo([root.x, root.y, root.r * 2 + margin]);

    function zoom(d) {
        var focus0 = focus;
        focus = d;

        var transition = transition()
            .duration(event.altKey ? 7500 : 750)
            .tween("zoom", function (d) {
                var i = interpolateZoom(view, [focus.x, focus.y, focus.r * 2 + margin]);
                return function (t) {
                    zoomTo(i(t));
                };
            });

        transition.selectAll("text")
            .filter(function (d) {
                return d && d.parent === focus || this.style.display === "inline";
            })
            .style("fill-opacity", function (d) {
                return d && d.parent === focus ? 1 : 0;
            })
            .on("start", function (d) {
                if (d && d.parent === focus) this.style.display = "inline";
            })
            .on("end", function (d) {
                if (d && d.parent !== focus) this.style.display = "none";
            });
    }

    function zoomTo(v) {
        var k = diameter / v[2];
        view = v;
        node.attr("transform", function (d) {
            return "translate(" + (d.x - v[0]) * k + "," + (d.y - v[1]) * k + ")";
        });
        circle.attr("r", function (d) {
            return d.r * k;
        });
    }
    return svg
}
export const Circles = () => {
    return (
        <>
        <svg width="960" height="960">
            <g transform="translate(480,480)"></g>
        </svg>
            <RenderCircle />
        </>
    )
}