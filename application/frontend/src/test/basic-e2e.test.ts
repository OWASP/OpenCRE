import puppeteer from 'puppeteer';
require('regenerator-runtime/runtime');

describe('App.js', () => {
  var browser;
  var page;
  const debug = {
    // headless: false,
    //  slowMo: 150,
    args: ['--no-sandbox', '--disable-setuid-sandbox'], // needed for docker, we trust the content of opencre.org
  };
  const config = {};
  beforeAll(async () => {
    jest.setTimeout(1000000);
    browser = await puppeteer.launch(debug);
    page = await browser.newPage();
    page.setDefaultTimeout(15000);
  });

  it('contains the welcome text', { url: 'http://localhost:5000' }, async () => {
    await page.goto('http://localhost:5000');
    await page.waitForSelector('#SearchBar');
    const text = await page.$eval('#SearchBar', (e) => e.textContent);
    expect(text).toContain('Search');
  });

  it('can search for random strs', { url: 'http://127.0.0.1:5000' }, async () => {
    await page.goto('http://127.0.0.1:5000');
    await page.waitForSelector('#SearchBar');
    await page.type('#SearchBar > div > input', 'asdf');
    await page.click('#SearchBar > div > button');
    await page.waitForSelector('.content');
    const text = await page.$eval('.content', (e) => e.textContent);
    expect(text).toContain('No results match your search term');
  });

  it(
    'can search for cryptography using the free text method and it returns both Nodes and CRES',
    { url: 'http://127.0.0.1:5000' },
    async () => {
      await page.goto('http://127.0.0.1:5000');
      await page.waitForSelector('#SearchBar');
      await page.type('#SearchBar > div > input', 'crypto');
      await page.click('#SearchBar > div > button');
      await page.waitForSelector('.content');
      const text = await page.$eval('.content', (e) => e.textContent);
      expect(text).not.toContain('No results match your search term');

      await page.waitForSelector('.standard-page__links-container');
      const results = await page.$$('.standard-page__links-container');
      expect(results.length).toBeGreaterThan(1);

      const cres = await page.$$('.cre-page >div>div>.standard-page__links-container');
      expect(cres.length).toBeGreaterThan(1);

      const docs = await page.$$('.cre-page >div>div:nth-child(2)>.standard-page__links-container');
      expect(docs.length).toBeGreaterThan(1);
    }
  );

  it(
    'can search for a standard by name, section and the standard page works as expected',
    { url: 'http://127.0.0.1:5000' },
    async () => {
      await page.goto('http://127.0.0.1:5000/node/standard/ASVS');
      await page.waitForSelector('.content');
      const text = await page.$$('.content', (e) => e.textContent);
      expect(text).not.toContain('No results match your search term');

      await page.waitForSelector('.standard-page__links-container');

      // title match
      const page_title = await page.$eval('.standard-page__heading', (e) => e.textContent);
      expect(page_title).toContain('ASVS');

      // results
      const results = await page.$$('.standard-page__links-container');
      expect(results.length).toBeGreaterThan(1);

      // pagination
      const original_content = await page.content();
      await page.click('a[type="pageItem"][value="2"]');
      await page.waitForSelector('.content');
      expect(await page.content()).not.toEqual(original_content);

      // link to section
      await page.click('.standard-page__links-container>.title>a');
      await page.waitForSelector('.content');
      const url = await page.url();
      expect(url).toContain('section');
      const section = await page.$eval('.standard-page > span:nth-child(2)', (e) => e.textContent);
      expect(section).toContain('Reference:');

      // show reference
      const hrefs = await page.evaluate(() =>
        Array.from(document.querySelectorAll('.section-page > a[href]'), (a) => a.getAttribute('href'))
      );
      expect(hrefs[0]).toContain('https://');

      // link to at least one cre
      const cre_links = await page.$$('.cre-page__links-container > .title > a:nth-child(1)');
      expect(cre_links.length).toBeGreaterThan(0);
      const cre_links_hrefs = await page.evaluate(() =>
        Array.from(document.querySelectorAll('.cre-page__links-container > .title > a:nth-child(1)'), (a) =>
          a.getAttribute('href')
        )
      );
      expect(cre_links_hrefs[0]).toContain('/cre/');
    }
  );

  it('can search for a cre', { url: 'http://127.0.0.1:5000' }, async () => {
    await page.goto('http://127.0.0.1:5000');
    await page.waitForSelector('#SearchBar');
    await page.type('#SearchBar > div > input', '558-807');
    await page.click('#SearchBar > div > button');
    await page.waitForSelector('.content');
    const text = await page.$$('.content', (e) => e.textContent);
    expect(text).not.toContain('No results match your search term');

    await page.waitForSelector('.standard-page__links-container');

    // title match
    const entry_title = await page.$eval('div.title.document-node', (e) => e.textContent);
    expect(entry_title).toContain('Mutually authenticate application and credential service provider');

    // results
    const results = await page.$$('.standard-page__links-container');
    expect(results.length).toBe(1);

    // // nesting
    await page.click('.dropdown');
    const selector =
      '.standard-page__links-container>.document-node>.document-node__link-type-container:nth-child(2)';
    await page.waitForSelector(selector);

    const nested = await page.$$(
      '.standard-page__links-container>.document-node>.document-node__link-type-container>div>.accordion'
    );
    expect(nested.length).toBeGreaterThan(1);
  });

  it('can filter', { url: 'http://127.0.0.1:5000' }, async () => {
    await page.goto('http://127.0.0.1:5000/cre/558-807?applyFilters=true&filters=asvs');
    await page.waitForSelector('.cre-page__links-container');
    // Get inner text
    const innerText = await page.evaluate(
      () => (document.querySelector('.cre-page__links-container') as HTMLElement)?.innerText
    );
    expect(innerText).toContain('ASVS');
    expect(innerText).toContain('CRE');
    expect(innerText).not.toContain('NIST');

    // ensure case insensitive filtering
    await page.goto('http://127.0.0.1:5000/cre/558-807?applyFilters=true&filters=ASVS');
    await page.waitForSelector('.cre-page__links-container');
    const intxt = await page.evaluate(
      () => (document.querySelector('.cre-page__links-container') as HTMLElement)?.innerText
    );
    expect(intxt).toContain('ASVS');
    expect(intxt).toContain('CRE');
    expect(intxt).not.toContain('NIST');

    const clearFilters = await page.evaluate(
      () => (document.querySelector('#clearFilterButton') as HTMLElement)?.innerText
    );
    expect(clearFilters).toContain('Clear Filters');
  });

  it('can smartlink', { url: 'http://127.0.0.1:5000' }, async () => {
    const response = await page.goto('http://127.0.0.1:5000/smartlink/standard/CWE/1002');
    expect(response.url()).toBe('http://127.0.0.1:5000/node/standard/CWE/sectionid/1002');

    const redirectResponse = await page.goto('http://127.0.0.1:5000/smartlink/standard/CWE/404');
    expect(redirectResponse.url()).toBe('https://cwe.mitre.org/data/definitions/404.html');
  });

  afterAll(async () => await browser.close());
});
