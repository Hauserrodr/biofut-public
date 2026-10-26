// SuperCopa sign-up counts for the bot (server.py copa_stats reads "inscritos" and "goleiros").
// Paste into the form's Apps Script (form editor > ⋮ > Apps Script), Deploy > New deployment > Web app,
// execute as me, access "Anyone"; put the /exec URL in BIOFUT_COPA_COUNT_URL on the server.
// Counts only: no names, e-mails or payment files ever leave the form.
function doGet() {
  const rs = FormApp.getActiveForm().getResponses();
  const c = {inscritos: rs.length, goleiros: 0, goleiros_reserva: 0, posicao: {}, churras: 0, camisetas: {}};
  const add = (o, k) => o[k] = (o[k] || 0) + 1;
  rs.forEach(r => r.getItemResponses().forEach(ir => {
    const t = ir.getItem().getTitle().trim(), v = ir.getResponse();
    if (t.startsWith('Posição Principal')) { add(c.posicao, v); if (v === 'Goleiro') c.goleiros++; }
    if (t.startsWith('Posição Secundária') && v === 'Goleiro') c.goleiros_reserva++;
    if (t.startsWith('Interesse no churras') && v === 'Vou participar') c.churras++;
    if (t.startsWith('Levantamento das camisetas')) [].concat(v).forEach(x => add(c.camisetas, x));
  }));
  return ContentService.createTextOutput(JSON.stringify(c)).setMimeType(ContentService.MimeType.JSON);
}
