
// function ChangeUrl(title, url) {
//     if (typeof (history.pushState) != "undefined") {
//         var obj = { Title: title, Url: url };
//         history.pushState(obj, obj.Title, obj.Url);
//     } else {
//         console.log('url rewriting will not work')
//     }
// }



function syntaxHighlight(input) {
    input = input.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return input.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        function (match) {
            var cls = 'number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'key';
                } else {
                    cls = 'string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'boolean';
            } else if (/null/.test(match)) {
                cls = 'null';
            }
            return $("<span/>", { "class": cls }).text(match);
        });
}


$('#old-results').hide()

function show_doc_collapsible(doc,container_div) {
    var txt
    if (doc.doctype == 'CRE'){
        txt = 'CRE: ' + doc.name +" - " + doc.id 
    }else{
        txt = 'Standard:' + doc.section + doc.subsection
    }
    var wrapper = $('<div class="panel panel-default">')
    var header = $('<div class="panel-heading active" role="tab">\
                    <h4 class="panel-title">')
    var a = $('<a role="button" data-toggle="collapse" data-parent="#accordion"  aria-expanded="true" aria-controls="collapseOne">')
    
    a.attr('href',href="#collapseOne")
    //  document.location.href + '?' + doc.doctype + '=' + doc.name) //
    a.text(txt)
    a.wrap(header)

    var section_wrap = $('<div id="collapseOne" class="panel-collapse collapse in" role="tabpanel">')
    var section = $('<div class="panel-body">')
    section.text(doc.description)
    section.wrap(section_wrap)
    
    a.append(section_wrap)
    a.wrap(wrapper)
    
    container_div.append(wrapper)
}
function make_h1(doc){
    var h1_txt = doc.doctype + " "
    if (doc.doctype == 'CRE') {
        h1_txt = h1_txt + doc.id + " "
    } 
    h1_txt = h1_txt + doc.name
    h1_txt = h1_txt + doc.section + " "
    h1_txt = h1_txt + doc.subsection+ " "

    return h1_txt
}
function visualise(documents) {
    for (const doc of documents) {
        $('#results').append($('<h5>').text(make_h1(doc)))
        $('#results').append($('<section>Is the same as </section>'))
        container_div = $('<div class="wrapper center-block">')
        container_div.append($('<div class="panel-group" id="accordion" role="tablist" aria-multiselectable="true">'))
        for (const el of doc.links) {
            show_doc_collapsible(el.document,container_div)
        }
        $('#results').append(container_div)

    }
}


function do_search(attr, val) {
    url = '/' + attr + '/' + val
    backend = '/rest/v1' + url
    // ChangeUrl('search',url)
    $.ajax({
        url: backend,
        type: "GET",
        dataType: "json",
        success: function (data) {
            yamlstr = YAML.stringify(YAML.parse(JSON.stringify(data)), 4);
            // console.log(yamlstr);
            visualise(data)
            // $('#results').append(yamlstr)
            // $('#results').show()
            $([document.documentElement, document.body]).animate({ scrollTop: $("#results").offset().top }, 2000);
        },
        error: function (error) {
            console.log(`Error ${error}`);
        }
    });
}
// var pathname = window.location.pathname;
// if (pathname.includes('/id/')){
//     do_search('id',pathname.replace('/rest/v1/id/'),"")
// }else if (pathname.includes('/name/')){
//     do_search('name',pathname.replace('/rest/v1/name/'),"")
// }else if (pathname.includes('/standard/')){
//     do_search('standard',pathname.replace('/rest/v1/standard/'),"")
// }

$('#CREsearchBtn').click(function () {
    switch ($('#CREsearchDropdown').val()) {
        case 'id':
            do_search('id', $('#CRESearchInput').val())
            break;
        case 'name':
            do_search('name', $('#CRESearchInput').val())
            break;
        case 'standard':
            do_search('standard', $('#CRESearchInput').val())
            break;
    }
})


$('.panel-collapse').on('show.bs.collapse', function () {
    $(this).siblings('.panel-heading').addClass('active');
  });
 
  $('.panel-collapse').on('hide.bs.collapse', function () {
    $(this).siblings('.panel-heading').removeClass('active');
  });