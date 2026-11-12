/* Run with Node and Playwright while FindBack is running locally. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {resolve} = require('node:path');
const {chromium} = require(process.env.FINDBACK_PLAYWRIGHT || 'playwright');

async function main() {
  const launch = {headless: true};
  if (process.env.FINDBACK_BROWSER) launch.executablePath = process.env.FINDBACK_BROWSER;
  let browser;
  let server;
  try {
    let url = process.env.FINDBACK_URL || 'http://127.0.0.1:8501/';
    if (process.env.FINDBACK_PYTHON) {
      server = spawn(process.env.FINDBACK_PYTHON, ['-m','findback.webapp','--port','0'],
        {cwd:resolve(__dirname,'..'),windowsHide:true,stdio:['ignore','pipe','inherit']});
      url = await new Promise((resolve,reject) => {
        server.once('error',reject);
        server.once('exit',code => reject(new Error(`Server exited: ${code}`)));
        let output = '';
        server.stdout.on('data', chunk => {
          output += chunk;
          const match = output.match(/http:\/\/127\.0\.0\.1:\d+\//);
          if (match) resolve(match[0]);
        });
      });
    }
    browser = await chromium.launch(launch);
    const page = await browser.newPage({viewport:{width:1440,height:1020}, acceptDownloads:true});
    page.setDefaultTimeout(8000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(url);
    await page.getByRole('heading', {name:'Наушники', exact:true}).waitFor();
    await page.locator('#recommendation').getByText('Проверить: Кафе', {exact:true}).waitFor();
    assert.equal(await page.locator('#map-pins button.pin').count(),5);
    if (process.env.FINDBACK_DESKTOP_CAPTURE) await page.screenshot({path:process.env.FINDBACK_DESKTOP_CAPTURE});

    async function report(id) {
      await page.getByRole('button',{name:'Добавить подсказку',exact:true}).click();
      await page.locator('#report-dialog summary').click();
      await page.locator('#report-id').fill(id);
      await page.locator('#report-target').selectOption('Library');
      await page.locator('#report-note').fill('Похожий кейс видели на стойке');
      await page.getByRole('button',{name:'Сохранить подсказку'}).click();
    }

    await report('witness-01');
    await page.locator('#belief').getByText('84,21 %',{exact:true}).waitFor();
    await page.locator('#history').getByText('Подсказка: Библиотека · Могли видеть вещь',{exact:true}).waitFor();
    await page.getByText('Похожий кейс видели на стойке',{exact:true}).waitFor();
    await page.locator('#report-dialog details').evaluate(el => { el.open = false; });
    await report('WITNESS-01');
    await page.getByText('Эта подсказка уже учтена. Проверь историю поиска.',{exact:true}).waitFor();
    await page.locator('#report-dialog').getByRole('button',{name:'Закрыть'}).click();
    assert.equal(await page.locator('#history > details').count(),1);

    await page.getByRole('button',{name:'Настроить проходы'}).click();
    await page.getByRole('button',{name:'Закрыть проход 0, 8',exact:true}).click();
    await page.getByRole('button',{name:'Открыть проход 0, 8',exact:true}).waitFor();
    await page.getByRole('button',{name:'Закрыть проход 1, 9',exact:true}).click();
    await page.getByRole('button',{name:'Открыть проход 1, 9',exact:true}).waitFor();
    await page.getByRole('button',{name:'Готово',exact:true}).click();
    await page.getByRole('button',{name:'Маршрут: Библиотека'}).click();
    await page.locator('#map-caption').getByText('С текущей позиции сюда нет маршрута.',{exact:true}).waitFor();
    await page.reload();
    await page.locator('#belief').getByText('84,21 %',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Маршрут: Библиотека'}).click();
    await page.locator('#map-caption').getByText('С текущей позиции сюда нет маршрута.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Как это работает',exact:true}).click();
    await page.locator('#show-expansion').check();
    await page.locator('#trace-range').focus();
    await page.keyboard.press('End');
    assert.ok(Number(await page.locator('#trace-range').inputValue()) > 0);
    await page.locator('#show-expansion').uncheck();
    await page.getByText('Планировщик Беллмана · 89 %',{exact:true}).waitFor();
    await page.locator('#experiment-scenario').selectOption('urgent');
    await page.getByText('Планировщик Беллмана · 34 %',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Поиск',exact:true}).click();
    const [download] = await Promise.all([
      page.waitForEvent('download'),page.getByRole('button',{name:'Скачать историю'}).click()
    ]);
    assert.equal(download.suggestedFilename(),'findback-search.json');

    await page.getByRole('button',{name:'Новый поиск',exact:false}).click();
    await page.locator('#item').fill('Ключи');
    await page.locator('#start-at').selectOption('Cafeteria');
    await page.locator('#last-seen').selectOption('Lab');
    await page.getByRole('button',{name:'Начать поиск',exact:true}).click();
    await page.getByRole('heading',{name:'Ключи',exact:true}).waitFor();
    assert.ok((await page.locator('[data-location="Lab"]').innerText()).includes('25'));
    await page.getByRole('button',{name:'Маршрут: Кафе'}).click();
    await page.getByRole('button',{name:'Записать проверку'}).click();
    await page.locator('#outcome').selectOption('not_found');
    await page.getByRole('button',{name:'Сохранить результат'}).click();
    await page.locator('#history').getByText('Проверка: Кафе · Вещь не найдена',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Мои поиски',exact:false}).click();
    await page.locator('.saved-item').filter({hasText:'Наушники'}).getByRole('button',{name:'Открыть'}).click();
    await page.getByRole('heading',{name:'Наушники',exact:true}).waitFor();
    await page.locator('#belief').getByText('84,21 %',{exact:true}).waitFor();

    await page.getByRole('button',{name:'Новый поиск',exact:false}).click();
    await page.locator('#item').fill('Наушники · симуляция');
    await page.locator('#start-at').selectOption('');
    await page.locator('#last-seen').selectOption('');
    await page.locator('#setup details').getByText('Настройки симуляции').click();
    await page.locator('#mode').selectOption('simulation');
    await page.getByRole('button',{name:'Начать поиск',exact:true}).click();
    await page.getByText('Учебный кампус · Симуляция',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Выполнить действие'}).click();
    await page.locator('#status').getByText('Вещь найдена',{exact:true}).waitFor();
    await page.locator('#budget-view').getByText('23 из 30 ед.',{exact:true}).waitFor();

    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth),390);
    await page.evaluate(() => window.scrollTo(0,0));
    if (process.env.FINDBACK_MOBILE_CAPTURE) await page.screenshot({path:process.env.FINDBACK_MOBILE_CAPTURE});
    assert.deepEqual(errors,[]);
    console.log('Browser checks passed: clues, duplicate, closures, reload, A* trace, export, comparisons, custom search, saved searches, seeded discovery and mobile layout.');
  } finally {
    if (browser) await browser.close();
    if (server) server.kill();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
