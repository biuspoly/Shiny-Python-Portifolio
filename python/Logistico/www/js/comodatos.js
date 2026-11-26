(function () {
  function limparSelecao(caixaSelectize) {
    var controle = caixaSelectize.closest(".selectize-control");
    var select = controle && controle.previousElementSibling;
    if (!select || !select.selectize) {
      select = controle && controle.parentElement.querySelector("select.selectized");
    }
    if (select && select.selectize) select.selectize.clear();
  }

  function criarResumo(caixaSelectize) {
    var resumo = document.createElement("div");
    resumo.className = "item comod-resumo-selecao";

    var limpar = document.createElement("a");
    limpar.href = "javascript:void(0)";
    limpar.className = "remove";
    limpar.title = "Remover todos";
    limpar.textContent = "×";
    limpar.addEventListener("click", function (evento) {
      evento.preventDefault();
      evento.stopPropagation();
      limparSelecao(caixaSelectize);
    });
    resumo.appendChild(limpar);

    var texto = document.createElement("span");
    texto.className = "comod-resumo-texto";
    resumo.appendChild(texto);
    caixaSelectize.insertBefore(resumo, caixaSelectize.querySelector("input"));
    return resumo;
  }

  function atualizarResumo(caixaSelectize) {
    var itens = caixaSelectize.querySelectorAll(":scope > .item:not(.comod-resumo-selecao)");
    var resumo = caixaSelectize.querySelector(".comod-resumo-selecao");

    itens.forEach(function (item) {
      if (item.querySelector(".comod-item-texto")) return;
      Array.from(item.childNodes).forEach(function (no) {
        if (no.nodeType !== Node.TEXT_NODE || !no.textContent.trim()) return;
        var texto = document.createElement("span");
        texto.className = "comod-item-texto";
        texto.textContent = no.textContent;
        item.replaceChild(texto, no);
      });
    });

    if (itens.length > 1) {
      var textoResumo = itens.length + " itens";
      itens.forEach(function (item) {
        item.classList.add("comod-item-oculto");
      });
      if (!resumo) resumo = criarResumo(caixaSelectize);
      var texto = resumo.querySelector(".comod-resumo-texto");
      if (texto.textContent !== textoResumo) texto.textContent = textoResumo;
      resumo.classList.remove("filtro-resumo-oculto");
    } else if (resumo) {

      resumo.classList.add("filtro-resumo-oculto");
      itens.forEach(function (item) {
        item.classList.remove("comod-item-oculto");
      });
    }
  }

  function varrerFiltrosComod() {
    document.querySelectorAll(".filtros-comod .selectize-input").forEach(atualizarResumo);
  }

  document.addEventListener("DOMContentLoaded", function () {
    varrerFiltrosComod();
    new MutationObserver(varrerFiltrosComod).observe(document.body, { childList: true, subtree: true });
  });
})();

(function () {
  var SUFIXOS_TABELA = [
    "-tabela_clientes", "-tabela_solicitacoes", "-tabela_pre_pedidos", "-tabela_comodatos",
  ];
  var MAPA_CLASSE_INPUT = {
    "comod-btn-solicitar": "clique_solicitar",
    "comod-btn-detalhes": "clique_detalhes",
    "comod-btn-sincronizar": "clique_sincronizar",
    "comod-btn-enviar": "clique_enviar",
    "comod-btn-retirar": "clique_retirar",

    "comod-btn-cancelar-solicitacao": "clique_cancelar_solicitacao",

    "comod-btn-cancelar-pre-pedido": "clique_cancelar_pre_pedido",
    "comod-btn-acao": "clique_acao",

    "comod-btn-reenviar": "clique_reenviar",
    "comod-btn-reenviar-travado": "clique_reenviar",

    "comod-btn-expandir": "clique_expandir",

    "comod-btn-recolha": "clique_recolha",
  };

  document.addEventListener("click", function (evento) {
    var botao = evento.target.closest(".comod-btn-cel");
    if (!botao) return;

    var nomeInput = null;
    for (var classe in MAPA_CLASSE_INPUT) {
      if (botao.classList.contains(classe)) {
        nomeInput = MAPA_CLASSE_INPUT[classe];
        break;
      }
    }
    if (!nomeInput) return;

    var wrapper = null;
    for (var i = 0; i < SUFIXOS_TABELA.length; i++) {
      wrapper = botao.closest('[id$="' + SUFIXOS_TABELA[i] + '"]');
      if (wrapper) break;
    }
    if (!wrapper) return;
    var sufixo = SUFIXOS_TABELA.find(function (s) {
      return wrapper.id.endsWith(s);
    });
    var ns = wrapper.id.slice(0, -sufixo.length);

    var dados = {};
    Array.from(botao.attributes).forEach(function (atributo) {
      if (atributo.name.indexOf("data-") === 0) {
        dados[atributo.name.slice(5).replace(/-/g, "_")] = atributo.value;
      }
    });
    Shiny.setInputValue(ns + "-" + nomeInput, dados, { priority: "event" });
  });

  var COLUNA_ORDENAVEL_HTML = "Solicitação";

  document.addEventListener("click", function (evento) {
    var th = evento.target.closest("th.header-html");
    if (!th || th.innerText.trim() !== COLUNA_ORDENAVEL_HTML) return;

    if (evento.target.closest(".tabela-resize-handle")) return;

    var wrapper = th.closest('[id$="-tabela_clientes"]');
    if (!wrapper) return;
    var ns = wrapper.id.slice(0, -"-tabela_clientes".length);
    Shiny.setInputValue(ns + "-clique_ordenar_solicitacao", { coluna: COLUNA_ORDENAVEL_HTML },
                        { priority: "event" });
  });
})();

(function () {
  var SUFIXO_TABELA = "-tabela_comodatos";
  var timerOcultar = null;
  var chaveAtual = null;

  function namespaceDe(elemento) {
    var wrapper = elemento.closest('[id$="' + SUFIXO_TABELA + '"]');
    return wrapper ? wrapper.id.slice(0, -SUFIXO_TABELA.length) : null;
  }

  function painel() {
    return document.getElementById("comod_produtos_panel");
  }

  window.comodProdutosOcultar = function () {

    timerOcultar = window.setTimeout(function () {
      var alvo = painel();
      if (alvo) alvo.classList.remove("comod-produtos-panel-visivel");
      chaveAtual = null;
    }, 250);
  };
  window.comodProdutosCancelarOcultar = function () {
    window.clearTimeout(timerOcultar);
  };

  function posicionar(evento) {
    var alvo = painel();
    if (!alvo) return;
    alvo.classList.add("comod-produtos-panel-visivel");
    var largura = alvo.offsetWidth || 620;
    var altura = alvo.offsetHeight || 260;
    var x = evento.clientX + 16;
    var y = evento.clientY + 16;
    if (x + largura > window.innerWidth) x = Math.max(8, window.innerWidth - largura - 8);
    if (y + altura > window.innerHeight) y = Math.max(8, window.innerHeight - altura - 8);
    alvo.style.left = x + "px";
    alvo.style.top = y + "px";
  }

  var COLUNA_LIMITE = "Produto";

  function limiteDaTabela(tabela) {
    if (!tabela) return -1;
    if (tabela.dataset.limiteHover === undefined) {
      var cabecalhos = tabela.querySelectorAll("thead th");
      var limite = -1;
      for (var i = 0; i < cabecalhos.length; i++) {
        if (cabecalhos[i].innerText.trim() === COLUNA_LIMITE) { limite = i; break; }
      }
      tabela.dataset.limiteHover = limite;
    }
    return parseInt(tabela.dataset.limiteHover, 10);
  }

  function alvoDoHover(elemento) {
    var marcado = elemento.closest("[data-tooltip-cev]");
    if (marcado) return marcado;
    var celula = elemento.closest("td");
    var linha = celula && celula.closest("tr");
    if (!linha) return null;
    var limite = limiteDaTabela(linha.closest("table"));
    if (limite < 0) return null;
    var posicao = Array.prototype.indexOf.call(linha.children, celula);
    if (posicao < 0 || posicao > limite) return null;
    return linha.querySelector("[data-tooltip-cev]");
  }

  document.addEventListener("mouseover", function (evento) {
    var celula = alvoDoHover(evento.target);
    if (!celula) return;
    var ns = namespaceDe(celula);
    if (!ns) return;
    window.comodProdutosCancelarOcultar();
    posicionar(evento);
    var chave = celula.getAttribute("data-tooltip-cev");
    if (chave === chaveAtual) return;
    chaveAtual = chave;
    Shiny.setInputValue(ns + "-cev_hover", chave, { priority: "event" });
  });

  document.addEventListener("mouseout", function (evento) {
    if (!alvoDoHover(evento.target)) return;

    window.comodProdutosOcultar();
  });

  document.addEventListener("click", function (evento) {

    if (evento.target.closest(".comod-btn-cel, a, .tabela-resize-handle")) return;
    var linha = evento.target.closest("tr");
    if (!linha) return;
    var celula = linha.querySelector("[data-tooltip-cev]");
    if (!celula) return;
    var ns = namespaceDe(celula);
    if (!ns) return;
    window.comodProdutosOcultar();
    Shiny.setInputValue(
      ns + "-clique_linha_cev",
      { chave_cev: celula.getAttribute("data-tooltip-cev"), momento: Date.now() },
      { priority: "event" }
    );
  });
})();

(function () {
  var observado = null;

  function liberar() {
    var botao = document.getElementById("bt_entendi_mudancas");
    if (botao) botao.disabled = false;
    var dica = document.getElementById("mudancas_dica");
    if (dica) dica.textContent = "Pode confirmar.";
  }

  function chegouAoFim(el) {
    return el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
  }

  function ligar() {
    var corpo = document.getElementById("mudancas_texto");
    if (!corpo) {
      observado = null;
      return;
    }
    if (corpo === observado) return;

    if (!corpo.clientHeight) return;
    observado = corpo;

    var fim = corpo.querySelector(".mudancas-fim");
    if (fim && window.IntersectionObserver) {
      new IntersectionObserver(function (entradas, observer) {
        if (!entradas.some(function (e) { return e.isIntersecting; })) return;
        liberar();
        observer.disconnect();
      }, { root: corpo, threshold: 0 }).observe(fim);
    }

    corpo.addEventListener("scroll", function aoRolar() {
      if (!chegouAoFim(corpo)) return;
      liberar();
      corpo.removeEventListener("scroll", aoRolar);
    });

    var modal = corpo.closest(".modal-body") || corpo.closest(".modal");
    if (modal && modal !== corpo) {
      modal.addEventListener("scroll", function aoRolarModal() {
        if (!chegouAoFim(modal)) return;
        liberar();
        modal.removeEventListener("scroll", aoRolarModal);
      });
    }

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (corpo.scrollHeight <= corpo.clientHeight + 2) liberar();
      });
    });
  }

  new MutationObserver(ligar).observe(document.body, { childList: true, subtree: true });
  ligar();
})();
