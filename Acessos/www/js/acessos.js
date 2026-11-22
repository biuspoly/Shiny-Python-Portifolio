(function () {
  var SUFIXO_TABELA = "-tabela";

  function namespaceDaTabela(elemento) {
    var saida = elemento.closest('[id$="' + SUFIXO_TABELA + '"]');
    if (!saida) return null;
    return saida.id.slice(0, -SUFIXO_TABELA.length);
  }

  document.addEventListener("change", function (evento) {
    var caixa = evento.target.closest(".acessos-checkbox-cel");
    if (!caixa) return;
    var ns = namespaceDaTabela(caixa);
    if (!ns) return;
    var valor = caixa.dataset.login + "|" + caixa.dataset.licenca + "|" + (caixa.checked ? "1" : "0");
    Shiny.setInputValue(ns + "-clique_check_revenda", valor, { priority: "event" });
  });

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".acessos-btn-remover");
    if (!botao) return;
    var ns = namespaceDaTabela(botao);
    if (!ns) return;
    var valor = botao.dataset.grupo + "|" + botao.dataset.painel;
    Shiny.setInputValue(ns + "-clique_remover_acesso", valor, { priority: "event" });
  });

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".acessos-btn-cel");
    if (!botao) return;
    var ns = namespaceDaTabela(botao);
    if (!ns) return;
    var valor = botao.dataset.pagina + "|" + botao.dataset.inativar;
    Shiny.setInputValue(ns + "-clique_situacao_pagina", valor, { priority: "event" });
  });

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".acessos-btn-excluir-cadastro");
    if (!botao) return;
    var ns = namespaceDaTabela(botao);
    if (!ns) return;
    var valor = botao.dataset.linha + "|" + botao.dataset.chave;
    Shiny.setInputValue(ns + "-clique_excluir", valor, { priority: "event" });
  });
})();
