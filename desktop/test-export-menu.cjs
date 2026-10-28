// Shared user-like navigation for existing portable-export regression journeys.
async function revealExport(page, name) {
  if (
    !["Export case file", "Export alerts", "Export captured records"].includes(
      name,
    )
  )
    return;
  const button = page.getByRole("button", {
    name,
    exact: true,
    includeHidden: true,
  });
  if (!(await button.isVisible())) {
    await button
      .locator("xpath=ancestor::details")
      .locator(":scope > summary")
      .click();
  }
}
module.exports = { revealExport };
