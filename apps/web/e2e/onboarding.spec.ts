import {test,expect} from '@playwright/test';

test('empty workspace and both AWS authentication methods',async({page},info)=>{
  await page.goto('/');
  await expect(page.getByRole('button',{name:/Open sample workspace/})).toHaveCount(0);
  await page.getByRole('button',{name:'Create a workspace',exact:true}).click();
  await page.getByLabel('Your name').fill('Workspace administrator');
  await page.getByLabel('Organization',{exact:true}).fill('Your workspace');
  await page.getByLabel('Email address').fill(`onboarding-${info.project.name}-${Date.now()}@example.test`);
  await page.getByLabel('Password',{exact:true}).fill('browser-test-local-password');
  await page.getByRole('button',{name:'Create workspace',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Cloud financial overview'})).toBeVisible();
  await expect(page.locator('.kpi-card').first()).toBeVisible();
  if(info.project.name==='desktop') await page.screenshot({path:'../../docs/images/overview.png',fullPage:true});
  await page.getByRole('button',{name:'Connect account',exact:true}).first().click();
  await expect(page.getByText('Sample account',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Continue',exact:true}).click();
  await page.getByLabel('Connection name').fill('Your AWS account');
  // This account ID is an isolated UI input; no provider call is made.
  await page.getByLabel('AWS account ID').fill('123456789012');
  await expect(page.getByLabel('Authentication method')).toHaveValue('role');
  await expect(page.getByLabel('Read-only role ARN')).toBeVisible();
  await page.getByLabel('Authentication method').selectOption('access_key');
  await expect(page.getByLabel('Access key ID',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Secret access key',{exact:true})).toHaveAttribute('type','password');
  if(info.project.name==='desktop') await page.screenshot({path:'../../docs/images/aws-onboarding.png',fullPage:true});
  await page.getByLabel('Access key ID',{exact:true}).fill('AKIA'+'A'.repeat(16));
  await page.getByLabel('Secret access key',{exact:true}).fill('b'.repeat(40));
  await page.getByRole('button',{name:'Review setup',exact:true}).click();
  await page.getByRole('button',{name:'Register connection',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Connection details'})).toBeVisible();
  await expect(page.getByText('Encrypted credentials are configured.',{exact:false})).toBeVisible();
  const storage=await page.evaluate(()=>JSON.stringify({local:{...localStorage},session:{...sessionStorage}}));
  expect(storage).not.toContain('AKIA'+'A'.repeat(16));
  const connections=await (await page.request.get('/v1/connections')).text();
  expect(connections).not.toContain('b'.repeat(40));
  expect(JSON.parse(connections).items[0].status).toBe('PENDING');
});
