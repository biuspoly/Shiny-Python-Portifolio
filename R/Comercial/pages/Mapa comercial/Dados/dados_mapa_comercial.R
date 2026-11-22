library(DBI)
library(stringr)
library(dplyr)
library(tidyr)
library(lubridate)
library(glue)
library(leaflet)
library(sf)
library(htmltools)
library(bsicons)
library(knitr)
library(echarts4r)

# Portfólio: o mesmo carregamento do cache que o Diário de Venda faz (dados_diario_venda_v8.R).
if (!exists("fonte_parquet_mc", mode = "function", inherits = TRUE)) {
  source(glue("{diretorio}Cache/Mapa comercial/cache_mapa_comercial.R"), local = TRUE, encoding = "UTF-8")
}


# Case canonical: revenda_query() retorna maiusculas; parquet usa proper-case
# (mesmo mapeamento usado em Diario de venda/Dados/dados_diario_venda_v8.R)

REVENDA_NOME_BD_MC <- list(
  "NATAL"        = "Natal",
  "ESPECIAL"       = "Especial",
  "SÃO LUÍS"     = "São Luís",
  "FORTALEZA"     = "Fortaleza",
  "TERESINA"     = "Teresina",
  "FILIAL A" = "Filial A",
  "FILIAL B" = "Filial B",
  "FILIAL B" = "Filial B",
  "FILIAL C"         = "Filial C",
  "FILIAL F"   = "Filial F",
  "FILIAL F"   = "Filial F",
  "FILIAL D"     = "Filial D",
  "FILIAL D"     = "Filial D",
  "FILIAL E"    = "Filial E"
)


# Filtro de revenda usado no WHERE de todas as queries da pagina ---------------
# Sempre UMA revenda: a agregacao de Filial D + Filial G dentro de Filial F
# vive no dado, nao aqui. tb_cidades_rev traz as cidades de Filial D/Filial G
# tambem no escopo de Filial F (como subrevendas, ver cidades_por_subrevenda
# em Acompanhamento Logistico/dados brutos/atualiza_cidades_rev.R) e
# atualiza_mapa_comercial.R replica venda/cliente/cobertura de Filial D para esse
# mesmo escopo. Expandir aqui tambem duplicaria cada cidade.
filtro_revenda_mc <- function(revenda, coluna = "REVENDA") {
  revenda_norm <- if (!is.null(REVENDA_NOME_BD_MC[[revenda]])) REVENDA_NOME_BD_MC[[revenda]] else revenda
  paste0(coluna, " IN ('", gsub("'", "''", revenda_norm), "')")
}


# Revendas com o botao Revenda/Fabrica ----------------------------------------
# Sao as que tem mais de uma SEDE de verdade. Nas outras sete o mapa usa sempre
# a distancia ate a FABRICA, e o botao nao aparece: em seis delas as duas
# distancias sao iguais (uma sede so, na propria cidade da fabrica), entao o
# botao nunca mudaria nada. Filial A fica de fora mesmo tendo duas
# subrevendas em tb_cidades_rev (19 cidades com distancia diferente): a segunda,
# Filial B2, e galpao, nao sede - entao a referencia dela e Filial A.
REVENDAS_ESCOLHE_DISTANCIA_MC <- c("Filial F", "Filial D", "Filial C", "Filial B")

escolhe_base_distancia_mc <- function(revenda) {
  revenda_norm <- if (!is.null(REVENDA_NOME_BD_MC[[revenda]])) REVENDA_NOME_BD_MC[[revenda]] else revenda
  revenda_norm %in% REVENDAS_ESCOLHE_DISTANCIA_MC
}


# Meses disponiveis (para o seletor da pagina) -------------------------------

meses_disponiveis_mc <- function(revenda) {

  filtro_revenda <- filtro_revenda_mc(revenda)

  meses <- fonte_parquet_mc(glue("
    SELECT DISTINCT MES
    FROM tb_cob_cid
    WHERE {filtro_revenda}
    ORDER BY MES DESC
  "))$MES

  # Diferente do Diario de Venda, aqui NAO forcamos o mes corrente do calendario:
  # a atualizacao do mapa (atualiza_mapa_comercial.R) roda por lote e pode nao
  # ter processado o mes atual ainda, o que deixaria o mapa sem cidades/geometria
  meses <- sort(unique(as.character(meses)), decreasing = TRUE)

  nomes_meses <- c("Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez")

  rotulos <- sapply(meses, function(m) {
    data <- as.Date(paste0(m, "01"), format = "%Y%m%d")
    paste0(nomes_meses[as.integer(format(data, "%m"))], "/", format(data, "%Y"))
  })

  setNames(as.character(meses), rotulos)
}


# Opcoes dos filtros de produto/vendedor (pickerInput multiplos da pagina) ----
# Todas as colunas so existem em TB_MAPA_POT, restritas ao que a revenda tem

opcoes_filtro_produto_mc <- function(revenda) {

  eh_especial     <- any(str_detect(toupper(revenda), "ESPECIAL"))
  coluna_marca   <- "MARCA"
  filtro_revenda <- filtro_revenda_mc(revenda)

  buscar_opcoes_coluna <- function(coluna, tabela = "tb_mapa_pot") {
    valores <- fonte_parquet_mc(glue("
      SELECT DISTINCT {coluna}
      FROM {tabela}
      WHERE {filtro_revenda} AND {coluna} IS NOT NULL
      ORDER BY {coluna}
    "))[[coluna]]
    sort(unique(as.character(valores)))
  }

  opcoes_canal <- buscar_opcoes_coluna("CANAL_PROD")
  if (!eh_especial) {
    opcoes_canal <- opcoes_canal[!toupper(trimws(opcoes_canal)) %in% c("CHOPP", "OUTRO")]
  }

  list(
    marca     = buscar_opcoes_coluna(coluna_marca),
    canal     = opcoes_canal,
    categoria = buscar_opcoes_coluna("SEGMENTO"),
    embalagem = buscar_opcoes_coluna("VOLUME"),
    vendedor  = buscar_opcoes_coluna("VEN"),
    # PORTE (classificacao do cliente) nao existe em tb_mapa_pot - vem de
    # tb_cli_ativos, mesma fonte usada no filtro em mapa_pot()
    porte     = buscar_opcoes_coluna("PORTE", tabela = "tb_cli_ativos")
  )
}


# Combinacoes reais de marca/canal/categoria/embalagem/vendedor em
# TB_MAPA_POT, usadas para o crossfilter dos pickerInput: ao escolher um
# valor num filtro, os outros so mostram opcoes que realmente coexistem com
# essa escolha (em vez da lista cheia, sempre igual, de opcoes_filtro_produto_mc)
combinacoes_filtro_produto_mc <- function(revenda) {

  eh_especial     <- any(str_detect(toupper(revenda), "ESPECIAL"))
  coluna_marca   <- "MARCA"
  filtro_revenda <- filtro_revenda_mc(revenda)

  combinacoes <- fonte_parquet_mc(glue("
    SELECT DISTINCT {coluna_marca} AS MARCA, CANAL_PROD, SEGMENTO, VOLUME, VEN
    FROM tb_mapa_pot
    WHERE {filtro_revenda}
  "))

  if (is.null(combinacoes)) return(combinacoes)

  combinacoes[] <- lapply(combinacoes, as.character)
  combinacoes
}


# Aba Mapa Potencial -----------------------------------------------------------

mapa_pot = function(revenda, mes_atual, marca = NULL, canal = NULL, categoria = NULL,
                     embalagem = NULL, ga = NULL, vendedor = NULL, porte = NULL,
                     base_distancia = "sede"){

  eh_especial   <- any(str_detect(toupper(revenda), "ESPECIAL"))
  coluna_marca <- "MP.MARCA"
  revenda <- if (!is.null(REVENDA_NOME_BD_MC[[revenda]])) REVENDA_NOME_BD_MC[[revenda]] else revenda

  # Filtro de revenda por alias da tabela: ja inclui as revendas agregadas
  # (ver REVENDA_AGREGA_MC no topo - Filial F traz Filial D junto)
  filtro_rev_mp <- filtro_revenda_mc(revenda, "MP.REVENDA")
  filtro_rev_cr <- filtro_revenda_mc(revenda, "CR.REVENDA")
  filtro_rev_c  <- filtro_revenda_mc(revenda, "C.REVENDA")
  filtro_rev_cc <- filtro_revenda_mc(revenda, "CC.REVENDA")

  # Filtros de produto/vendedor: essas colunas existem em TB_MAPA_POT, entao
  # sempre entram nas queries que leem essa tabela (query_venda e
  # query_venda_hist). GA e VEN tambem existem em TB_CLI_ATIVOS/TB_CLI_INATIVOS
  # (ver filtro_ga_c/filtro_ven_c abaixo) e por isso filtram clientes tambem;
  # marca/canal/categoria/embalagem ficam restritos a venda mesmo. Cada picker
  # vazio (NULL/character(0)) = "Todos" nesse campo
  filtro_sql_in <- function(coluna, valores) {
    if (length(valores) == 0) return("")
    valores_escapados <- gsub("'", "''", valores)
    lista <- paste0("'", valores_escapados, "'", collapse = ", ")
    glue("AND {coluna} IN ({lista})")
  }

  filtro_produto <- paste(
    filtro_sql_in(coluna_marca,     marca),
    filtro_sql_in("MP.CANAL_PROD", canal),
    filtro_sql_in("MP.SEGMENTO",   categoria),
    filtro_sql_in("MP.VOLUME",     embalagem),
    filtro_sql_in("MP.GA",         ga),
    filtro_sql_in("MP.VEN",        vendedor)
  )

  # PORTE (Classificacao Cliente) nao existe em TB_MAPA_POT, entao nao entra em
  # filtro_produto - existe em TB_COB_CID/TB_CLI_ATIVOS/TB_CLI_INATIVOS, cada uma
  # com um alias diferente nas queries abaixo (C. ou CC.)
  filtro_porte_c  <- filtro_sql_in("C.PORTE",  porte)
  filtro_porte_cc <- filtro_sql_in("CC.PORTE", porte)

  # GA e Vendedor sao atributos do cliente (nao so do produto vendido) e
  # tambem existem em TB_CLI_ATIVOS/TB_CLI_INATIVOS - entao, alem de
  # filtro_produto (venda), entram tambem nas queries de clientes (query_cli,
  # query_cli_inat, query_cli_hist), pra "Clientes"/"% Ativos" na aba Saiba
  # Mais e o card/coluna de Clientes no mapa acompanharem o filtro. TB_COB_CID
  # nao tem GA/VEN (so PORTE/CANAL), entao cobertura por cidade fica de fora.
  filtro_ga_c   <- filtro_sql_in("C.GA",   ga)
  filtro_ga_cc  <- filtro_sql_in("CC.GA",  ga)
  filtro_ven_c  <- filtro_sql_in("C.VEN",  vendedor)
  filtro_ven_cc <- filtro_sql_in("CC.VEN", vendedor)

  # Base da distancia (botao "Revenda" / "Fábrica" na pagina) -----------------
  # TB_CIDADES_REV traz as duas distancias calculadas separadamente em
  # atualiza_cidades_rev.R: DIST_SEDE (cidade -> sede da SUBREVENDA que a
  # atende) e DIST_FAB (cidade -> cidade da REVENDA, a fabrica/matriz). Tudo
  # que deriva de distancia (faixas de cor da borda, ordem de desenho dos
  # contornos e a legenda) usa a coluna escolhida aqui, sem misturar as duas.
  # Revenda sem o botao usa sempre a fabrica - vale mesmo se a chamada vier com
  # "sede" (o botao nem existe na tela nesse caso, ver
  # REVENDAS_ESCOLHE_DISTANCIA_MC no topo). "revenda" aqui ja esta normalizado.
  if (!(revenda %in% REVENDAS_ESCOLHE_DISTANCIA_MC)) base_distancia <- "fabrica"
  dist_fabrica     <- identical(base_distancia, "fabrica")
  coluna_distancia <- if (dist_fabrica) "CR.DIST_FAB" else "CR.DIST_SEDE"
  # Titulo e faixa de distancia zero ficam fixos: so a coluna usada muda com o
  # botao, a legenda em si nao troca de texto
  rotulo_distancia <- "Distância"
  rotulo_dist_zero <- "Sede"

  # Cores da borda (faixa de distancia da cidade ate a sede) -----------------
  cor_borda_sede  = "#3B2110"
  cor_borda_75    = "#006400"
  cor_borda_150   = "#be9c00"
  cor_borda_150_m = "#FF0000"
  cor_borda_200   = "#ADD8E6"
  cor_borda_na    = "#808080" # sem DISTANCIA cadastrada em tb_cidades_rev
  cor_borda_padrao = "#000000"

  # Especial nao usa faixa de distancia: borda preta padrao e nenhuma legenda de
  # Distancia - confirmado pelo usuario, e assim mesmo. As outras 10 revendas
  # tem a legenda (nao confundir com o BOTAO Revenda/Fabrica, que e so pras 4
  # de REVENDAS_ESCOLHE_DISTANCIA_MC).
  sem_distancia <- str_detect(toupper(revenda), toupper("Especial"))

  # Cores da area (faixa de cobertura sobre o potencial) ---------------------
  # marrom (mesmo tom da faixa de sede na distancia) para cobertura estourada
  cor_area_100 = "#3B2110"
  cor_area_75  = "#006400"
  cor_area_55  = "#be9c00"
  cor_area_0_m = "#FF0000"
  cor_area_0   = "#ADD8E6"

  # Cores do card do mapa ------------------------------------------------------
  cor_icone_card = "#006400"
  cor_texto_card = "#555"
  cor_texto_card2= "#FF0000"
  cor_texto_card3= "#be9c00"

  # Fator Maré -----------------------------------------------------------
  if(str_detect(toupper(revenda), toupper("Especial"))){
    fator_MAR = 2300
  } else{
    fator_MAR = 190
  }
  
  # Historico do tooltip (ultimos 4 meses, ancorado no mes atual da analise) --
  data_mes_atual   = as.Date(glue("{mes_atual}01"), format = "%Y%m%d")
  meses_historico  = format(seq(data_mes_atual, by = "-1 month", length.out = 4)[4:1], "%Y%m")

  sql_cor_borda <- if (sem_distancia) {
    glue("'{cor_borda_padrao}'")
  } else {
    glue("
      CASE
        WHEN {coluna_distancia} = 0 THEN '{cor_borda_sede}'
        WHEN {coluna_distancia} > 0 AND {coluna_distancia} <= 75 THEN '{cor_borda_75}'
        WHEN {coluna_distancia} > 75 AND {coluna_distancia} <= 150 THEN '{cor_borda_150}'
        WHEN {coluna_distancia} > 150 AND {coluna_distancia} < 200 THEN '{cor_borda_150_m}'
        WHEN {coluna_distancia} >= 200 THEN '{cor_borda_200}'
        ELSE '{cor_borda_na}'
      END")
  }

  query_venda = glue("SELECT
                  MP.*
               FROM TB_MAPA_POT MP
               WHERE {filtro_rev_mp}
                  AND MP.MES IN ({mes_atual})
                  {filtro_produto}")
  query_cid = glue("SELECT
                    CR.REVENDA,
                      CR.CIDADE,
                      CR.COD_IBGE,
                      CR.UF,
                      -- SUBREVENDA como AGREGADO, nao no GROUP BY: a Natal tem
                      -- 3 subrevendas com a MESMA sede (Natal, Natal Linha B,
                      -- Natal), entao cada cidade dela tem 3 linhas em
                      -- tb_cidades_rev, iguais em tudo menos nesse nome. Agrupar
                      -- por SUBREVENDA transformava 8 municipios em 24 - poligono
                      -- desenhado 3x e populacao somada 3x (medido: 1.192.305
                      -- virava 3.576.915). Nas outras 10 revendas a cidade tem uma
                      -- subrevenda so, entao MIN e ela mesma.
                      MIN(CR.SUBREVENDA) AS SUBREVENDA,
                      COUNT(DISTINCT CC.CLI) AS QTD_PDV,
                      ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) AS COB_POT,
                      CR.POPULACAO,
                      CEILING(CR.POPULACAO / {fator_MAR}) AS POTENCIAL,
                      CASE
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 55 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 75 THEN CEILING(CEILING(CR.POPULACAO / {fator_MAR}) * 0.75) - COUNT(DISTINCT CC.CLI)
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 0 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 55 THEN CEILING(CEILING(CR.POPULACAO / {fator_MAR}) * 0.55) - COUNT(DISTINCT CC.CLI)
                        ELSE 0
                      END AS POT_PROX_NVL,
                      {coluna_distancia} AS DISTANCIA,
                      {sql_cor_borda} AS COR_BORDA,
                      CASE
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 100 THEN '{cor_area_100}'
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 75 THEN '{cor_area_75}'
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 55 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 75 THEN '{cor_area_55}'
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) > 0 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 55 THEN '{cor_area_0_m}'
                        ELSE '{cor_area_0}'
                      END AS COR_AREA,
                      CASE
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 55 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 75 THEN '{cor_area_75}'
                        WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 0 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 55 THEN '{cor_area_55}'
                        ELSE '0'
                      END AS COR_POT_PROX_NVL,
                      CR.GEOMETRY
                  FROM TB_CIDADES_REV CR
                  LEFT JOIN TB_COB_CID CC
                    ON CC.REVENDA = CR.REVENDA
                      AND CC.COD_IBGE = CR.COD_IBGE
                  WHERE {filtro_rev_cr}
                    AND CC.MES IN ({mes_atual})
                    {filtro_porte_cc}
                  GROUP BY CR.REVENDA, CR.CIDADE, CR.COD_IBGE, CR.UF, CR.POPULACAO, {coluna_distancia}, CR.GEOMETRY;
                  ")
  query_cli = glue("SELECT
                  C.*
               FROM TB_CLI_ATIVOS C
               WHERE {filtro_rev_c}
                   AND C.MES IN ({mes_atual})
                   {filtro_porte_c}
                   {filtro_ga_c}
                   {filtro_ven_c}")

  query_cli_inat = glue("SELECT
                  C.*
               FROM TB_CLI_INATIVOS C
               WHERE {filtro_rev_c}
                   AND C.MES IN ({mes_atual})
                   {filtro_porte_c}
                   {filtro_ga_c}
                   {filtro_ven_c}")

  query_cob = glue("SELECT
                C.MES,
                COUNT(DISTINCT C.CLI) AS QTD_PDV
               FROM TB_COB_CID C
               WHERE {filtro_rev_c}
                 {filtro_porte_c}
               GROUP BY C.MES")

  # Historico por cidade (ultimos 4 meses) para o tooltip do mapa ------------
  meses_in = paste(meses_historico, collapse = ",")

  query_cob_hist = glue("SELECT
                  CC.COD_IBGE,
                  CC.MES,
                  COUNT(DISTINCT CC.CLI) AS QTD_PDV,
                  CASE
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 55 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 75 THEN CEILING(CEILING(CR.POPULACAO / {fator_MAR}) * 0.75) - COUNT(DISTINCT CC.CLI)
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 0 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 55 THEN CEILING(CEILING(CR.POPULACAO / {fator_MAR}) * 0.55) - COUNT(DISTINCT CC.CLI)
                    ELSE 0
                  END AS POT_PROX_NVL,
                  CASE
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 55 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 75 THEN '{cor_area_75}'
                    WHEN ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) >= 0 AND ROUND(COUNT(DISTINCT CC.CLI) / CEILING(CR.POPULACAO / {fator_MAR}) * 100, 2) < 55 THEN '{cor_area_55}'
                    ELSE '0'
                  END AS COR_POT_PROX_NVL
               FROM TB_COB_CID CC
               JOIN TB_CIDADES_REV CR
                 ON CR.REVENDA = CC.REVENDA
                   AND CR.COD_IBGE = CC.COD_IBGE
               WHERE {filtro_rev_cc}
                 AND CC.MES IN ({meses_in})
                 {filtro_porte_cc}
               GROUP BY CC.COD_IBGE, CC.MES, CR.POPULACAO")

  query_venda_hist = glue("SELECT
                  MP.COD_IBGE,
                  MP.MES,
                  SUM(MP.QTD_TOTAL_HL) AS VOLUME_HL,
                  SUM(MP.QTD_TOTAL) AS QTD_UMB
               FROM TB_MAPA_POT MP
               WHERE {filtro_rev_mp}
                 AND MP.MES IN ({meses_in})
                 {filtro_produto}
               GROUP BY MP.COD_IBGE, MP.MES")

  query_cli_hist = glue("SELECT
                  CC.COD_IBGE,
                  CC.MES,
                  COUNT(DISTINCT CC.CLI_ATIVO) AS CLI_ATIVO
               FROM TB_CLI_ATIVOS CC
               WHERE {filtro_rev_cc}
                 AND CC.MES IN ({meses_in})
                 {filtro_porte_cc}
                 {filtro_ga_cc}
                 {filtro_ven_cc}
               GROUP BY CC.COD_IBGE, CC.MES")

  # Leitura via parquet/DuckDB (Cache/Mapa comercial/cache_mapa_comercial.R) --
  # em vez de bater direto no MariaDB a cada troca de filtro

  venda           = fonte_parquet_mc(query_venda)
  cidades         = fonte_parquet_mc(query_cid)

  # Guarda contra mes sem dados ainda processados por atualiza_mapa_comercial.R
  # (sem isso, cidades_sf ficaria vazio e quebraria o bbox do leaflet)
  if (is.null(cidades) || nrow(cidades) == 0) {
    stop(glue("Sem dados de cobertura para {revenda} no mes {mes_atual}."), call. = FALSE)
  }

  clientes_ativos = fonte_parquet_mc(query_cli)
  clientes_inativos = fonte_parquet_mc(query_cli_inat)
  cobertura       = fonte_parquet_mc(query_cob)
  cob_hist_cid    = fonte_parquet_mc(query_cob_hist)
  venda_hist_cid  = fonte_parquet_mc(query_venda_hist)
  cli_hist_cid  = fonte_parquet_mc(query_cli_hist)

  cli_cid = clientes_ativos |>
    group_by(COD_IBGE) |>
    summarise(CLI_ATIVO = n_distinct(CLI_ATIVO, na.rm = TRUE))
  cidades = left_join(cidades, cli_cid, by = c("COD_IBGE"))
  venda_cid = venda |>
    group_by(COD_IBGE) |>
    summarise(
      FATURAMENTO = sum(FATURAMENTO, na.rm = TRUE),
      VOLUME_HL   = ceiling(sum(QTD_TOTAL_HL, na.rm = TRUE)),
      QTD_UMB     = ceiling(sum(QTD_TOTAL, na.rm = TRUE)),
      .groups     = "drop"
    )
  cidades = left_join(cidades, venda_cid, by = c("COD_IBGE"))
  cidades$FATURAMENTO = coalesce(cidades$FATURAMENTO, 0)
  cidades$VOLUME_HL = coalesce(cidades$VOLUME_HL, 0)
  cidades$QTD_UMB = coalesce(cidades$QTD_UMB, 0)
  cidades$FAT_HAB = round(coalesce(cidades$FATURAMENTO / cidades$POPULACAO, 0), 2)
  cidades$CLI_ATIVO[is.na(cidades$CLI_ATIVO)] = 0
  
  cli_hist_cid$MES = as.character(cli_hist_cid$MES)
  # Cards -------------------------------------------------------------------
  
  fator     = fator_MAR

  clientes  = n_distinct(clientes_ativos$CLI_ATIVO, na.rm = TRUE)
  populacao = sum(cidades$POPULACAO, na.rm = TRUE)
  potencial = ceiling(populacao / fator)
  volume_hl = ceiling(sum(venda$QTD_TOTAL_HL, na.rm = TRUE))
  qtd_umb   = ceiling(sum(venda$QTD_TOTAL, na.rm = TRUE))
  fat_hab   = round(coalesce(sum(venda$FATURAMENTO, na.rm = TRUE)/populacao,0), 2)
  cobertura_atual = sum(cobertura$QTD_PDV[cobertura$MES == mes_atual], na.rm = TRUE)
  
  cob_pot   = round(cobertura_atual/potencial, 4) * 100
  perc_cli_ativo = round(cobertura_atual/clientes, 4) * 100
  mun_amarelo = sum(cidades$COR_POT_PROX_NVL == cor_area_55, na.rm = TRUE)
  cob_amarelo = sum(cidades$QTD_PDV[cidades$COR_POT_PROX_NVL == cor_area_55], na.rm = TRUE)
  
  cob_hist     = cobertura$QTD_PDV
  cli_hist     = cob_hist_cid |>
    left_join(
      cli_hist_cid |> group_by(MES, COD_IBGE) |> summarise(CLI_ATIVO = sum(CLI_ATIVO, na.rm = TRUE)),
      by = c("MES", "COD_IBGE")
    ) |>
    mutate(PERC_COB_CLI = round(QTD_PDV/CLI_ATIVO, 4) * 100)
  cli_hist$PERC_COB_CLI[is.na(cli_hist$PERC_COB_CLI)] = 0
  
  cob_cli_hist = cli_hist |> select(COD_IBGE, MES, PERC_COB_CLI)
  cob_pot_hist = round(cob_hist / potencial, 4) * 100

  # Grafico historico de cobertura (addControl bottomright) ------------------
  meses_pt <- c("janeiro","fevereiro","março","abril","maio","junho",
                "julho","agosto","setembro","outubro","novembro","dezembro")

  mes_ano_label <- function(mes_yyyymm) {
    ano <- substr(as.character(mes_yyyymm), 1, 4)
    mn  <- as.integer(substr(as.character(mes_yyyymm), 5, 6))
    glue("{meses_pt[mn]}/{ano}")
  }

  grafico_cob_df <- cobertura %>%
    arrange(MES) %>%
    mutate(
      QTD_PDV      = as.numeric(QTD_PDV),
      COB_POT_HIST = round(QTD_PDV / potencial, 4) * 100,
      LABEL        = mes_ano_label(MES)
    )
  grafico_cob_df$LABEL[nrow(grafico_cob_df)] <- "Mês Atual"

  cob_pot_hist_js <- paste0("[", paste(grafico_cob_df$COB_POT_HIST, collapse = ","), "]")

  grafico_cob_opts <- list(
    grid = list(top = 22, bottom = 32, left = 12, right = 12, containLabel = TRUE),
    xAxis = list(type = "category", data = as.list(grafico_cob_df$LABEL),
                 axisTick = list(show = FALSE), axisLine = list(show = FALSE),
                 axisLabel = list(fontSize = 10)),
    yAxis = list(show = FALSE, min = 0, max = max(grafico_cob_df$QTD_PDV) * 1.3),
    series = list(
      list(
        type = "line", smooth = TRUE, symbol = "circle", symbolSize = 5,
        areaStyle = list(opacity = 0.25, color = cor_icone_card),
        lineStyle = list(color = cor_icone_card, width = 2),
        itemStyle = list(color = cor_icone_card),
        data = grafico_cob_df$QTD_PDV,
        label = list(show = TRUE, position = "bottom", fontSize = 10, color = "#333",
                     formatter = "{c}")
      ),
      list(
        type = "line", smooth = TRUE, symbol = "circle", symbolSize = 5, silent = TRUE,
        lineStyle = list(color = cor_icone_card, width = 2),
        itemStyle = list(color = cor_icone_card),
        data = grafico_cob_df$QTD_PDV,
        label = list(
          show = TRUE, position = "top", fontSize = 10,
          formatter = htmlwidgets::JS(sprintf(
            "function(p){ var v = %s; return v[p.dataIndex] + '%%'; }",
            cob_pot_hist_js
          ))
        )
      )
    )
  )

  grafico_cobertura <- echarts4r::e_charts(width = "480px", height = "16vh") %>%
    echarts4r::e_list(grafico_cob_opts)

  # Historico por cidade (para o tooltip) ------------------------------------
  historico_cid = cob_hist_cid %>%
    full_join(cob_cli_hist, by = c("COD_IBGE", "MES")) %>%
    full_join(venda_hist_cid, by = c("COD_IBGE", "MES")) %>%
    mutate(
      QTD_PDV      = coalesce(as.numeric(QTD_PDV), 0),
      VOLUME_HL    = coalesce(as.numeric(VOLUME_HL), 0),
      QTD_UMB      = coalesce(as.numeric(QTD_UMB), 0),
      PERC_COB_CLI     = coalesce(as.numeric(PERC_COB_CLI), 0),
      POT_PROX_NVL     = coalesce(as.numeric(POT_PROX_NVL), 0),
      COR_POT_PROX_NVL = coalesce(as.character(COR_POT_PROX_NVL), cor_texto_card)
    )


  # =====================================================
  # MAPA (LEAFLET) -------------------------------------------------------------
  # =====================================================

  parse_geojson_geom <- function(geojson_txt) {
    tryCatch(
      st_geometry(st_read(geojson_txt, quiet = TRUE))[[1]],
      error = function(e) st_polygon()
    )
  }

  cidades_geo <- cidades %>%
    filter(!is.na(GEOMETRY))
  cidades_geo$geometry <- st_sfc(lapply(cidades_geo$GEOMETRY, parse_geojson_geom), crs = 4326)
  cidades_sf <- st_as_sf(cidades_geo)

  # ordem de desenho das bordas: sede por cima, 200km por baixo
  # (poligonos desenhados depois ficam sobrepostos aos anteriores)
  ordem_borda <- c(cor_borda_padrao, cor_borda_na, cor_borda_200, cor_borda_150_m, cor_borda_150, cor_borda_75, cor_borda_sede)
  cidades_sf <- cidades_sf %>%
    mutate(COR_BORDA = factor(COR_BORDA, levels = ordem_borda)) %>%
    arrange(COR_BORDA) %>%
    mutate(COR_BORDA = as.character(COR_BORDA))

  # Une os municipios da mesma faixa para desenhar apenas o contorno externo.
  # A projecao plana + reparo evita falhas de auto-intersecao (Filial A).
  contornos_borda_sf <- cidades_sf %>%
    st_transform(3857) %>%
    st_make_valid() %>%
    st_buffer(0) %>%
    mutate(COR_BORDA = factor(COR_BORDA, levels = ordem_borda)) %>%
    group_by(COR_BORDA) %>%
    summarise(geometry = st_union(geometry), .groups = "drop") %>%
    arrange(COR_BORDA) %>%
    mutate(COR_BORDA = as.character(COR_BORDA)) %>%
    st_transform(4326)

  mapa_tooltip <- function(linha, historico) {
    hist_cidade <- historico %>%
      filter(COD_IBGE == linha$COD_IBGE) %>%
      arrange(MES)

    meses_label <- format(as.Date(glue("{hist_cidade$MES}01"), format = "%Y%m%d"), "%b/%y")

    falta_prox_nivel <- glue(
      "<span style='color:{hist_cidade$COR_POT_PROX_NVL}'>{hist_cidade$POT_PROX_NVL}</span>"
    )

    tabela_hist <- data.frame(
      "Cobertura"    = hist_cidade$QTD_PDV,
      "% Cobertura"  = glue("{hist_cidade$PERC_COB_CLI}%"),
      "% Potencial"  = glue("{round(hist_cidade$QTD_PDV / linha$POTENCIAL * 100, 1)}%"),
      "Volume HL"    = ceiling(hist_cidade$VOLUME_HL),
      "Qtd UMB"      = hist_cidade$QTD_UMB,
      "Falta p/ próx. nível" = falta_prox_nivel,
      check.names = FALSE
    )
    tabela_hist_t <- as.data.frame(t(tabela_hist))
    names(tabela_hist_t) <- meses_label

    tooltip_tag <- tags$div(
      style = "font-family: sans-serif; font-size: 11px; min-width: 215px; padding: 2px;",
      tags$h4(style = "text-align: center; margin: 2px 0; font-size: 13px;", linha$CIDADE),
      tags$table(
        style = "width: 100%;",
        tags$tr(tags$td("População:"), tags$td(style = "text-align: right;", format(linha$POPULACAO, big.mark = ".", decimal.mark = ","))),
        tags$tr(tags$td("Clientes:"), tags$td(style = "text-align: right;", linha$CLI_ATIVO)),
        tags$tr(tags$td("R$ / Hab:"), tags$td(style = "text-align: right;", glue("R$ {format(linha$FAT_HAB, big.mark = '.', decimal.mark = ',')}"))),
        tags$tr(tags$td("Potencial:"), tags$td(style = "text-align: right;", linha$POTENCIAL)),
        tags$tr(tags$td("Falta p/ próx. nível:"), tags$td(style = glue("text-align: right; color:{linha$COR_POT_PROX_NVL};"), linha$POT_PROX_NVL))
      ),
      tags$div(
        style = "background: #888; color: white; text-align: center; font-weight: bold; margin-top: 5px; padding: 2px 0; font-size: 11px;",
        "Histórico"
      ),
      tags$style(HTML(".mapa-tooltip-hist td, .mapa-tooltip-hist th { padding: 2px 7px; font-size: 11px; }")),
      tags$div(class = "mapa-tooltip-hist", HTML(as.character(kable(tabela_hist_t, format = "html", escape = FALSE))))
    )

    HTML(as.character(tooltip_tag))
  }

  cidades_tooltip <- lapply(seq_len(nrow(cidades_sf)), function(i) mapa_tooltip(cidades_sf[i, ], historico_cid))

  mapa_card <- function(titulo, valor, cor_icone, cor_titulo = cor_texto_card, icone = "people-fill") {
    tags$div(
      style = "display: flex; align-items: center; gap: clamp(4px, 0.5vw, 8px);
                min-width: clamp(90px, 11vw, 145px);
                padding: clamp(4px, 0.45vw, 8px);
                background: rgba(255,255,255,0.8);
                box-shadow: 0 0 15px rgba(0,0,0,0.2);
                border-radius: 5px;
                font-size: clamp(11px, 0.85vw, 14px);",
      tags$span(
        style = glue("font-size: clamp(20px, 2.2vw, 30px); color: {cor_icone};"),
        bs_icon(icone)
      ),
      tags$div(
        style = glue("color: {cor_titulo};"),
        tags$strong(titulo), tags$br(),
        valor
      )
    )
  }

  # Cards -------------------------------------------------------------------
  # Antes desenhados dentro do leaflet via addControl; agora ficam de fora,
  # renderizados num absolutePanel por cima do mapa (ver pag_mapa_comercial_novo.R)

  cards_topo <- tags$div(
    style = "display: flex; flex-direction: column; gap: clamp(4px, 0.5vw, 8px);",
    tags$div(
      style = "display: flex; flex-direction: row; flex-wrap: wrap; gap: clamp(4px, 0.5vw, 8px);",
      mapa_card("Clientes",  format(clientes,  big.mark = ".", decimal.mark = ","), cor_icone_card, cor_titulo = cor_texto_card),
      mapa_card("Volume HL", format(volume_hl, big.mark = ".", decimal.mark = ","), cor_icone_card, cor_titulo = cor_texto_card, icone = "droplet"),
      mapa_card("Cobertura", glue("{format(cobertura_atual, big.mark = '.', decimal.mark = ',')} ({format(perc_cli_ativo, big.mark = '.', decimal.mark = ',', nsmall = 2)}%)"), cor_icone_card, cor_titulo = cor_texto_card, icone = "person-check-fill"),
      mapa_card("R$ / Hab", glue("R$ {format(fat_hab, big.mark = '.', decimal.mark = ',')}"), cor_icone_card, cor_titulo = cor_texto_card, icone = "houses"),
      mapa_card("Cob Amarela", format(cob_amarelo, big.mark = ".", decimal.mark = ","), cor_texto_card3, cor_titulo = cor_texto_card3, icone = "circle-fill"),
      mapa_card("Fator", format(fator, big.mark = ".", decimal.mark = ","), cor_texto_card, cor_titulo = cor_texto_card, icone = "rulers")
    ),
    tags$div(
      style = "display: flex; flex-direction: row; flex-wrap: wrap; gap: clamp(4px, 0.5vw, 8px);",
      mapa_card("Potencial", format(potencial, big.mark = ".", decimal.mark = ","), cor_texto_card, cor_titulo = cor_texto_card),
      mapa_card("Volume UMB", format(qtd_umb, big.mark = ".", decimal.mark = ","), cor_icone_card, cor_titulo = cor_texto_card, icone = "box"),
      mapa_card("Cob. Potencial", glue("{format(cob_pot, big.mark = '.', decimal.mark = ',', nsmall = 2)}%"), cor_texto_card, cor_titulo = cor_texto_card, icone = "person-check-fill"),
      mapa_card("População", format(populacao, big.mark = ".", decimal.mark = ","), cor_icone_card, cor_titulo = cor_texto_card, icone = "globe2"),
      mapa_card("Mun Amarelos", format(mun_amarelo, big.mark = ".", decimal.mark = ","), cor_texto_card3, cor_titulo = cor_texto_card3, icone = "pin-map-fill")
    )
  )

  mapa_com <- leaflet(cidades_sf) %>%
    addProviderTiles(providers$OpenStreetMap) %>%  # Portfólio: o CartoDB.Positron do original agora pede chave de acesso
    # Camada municipal: preenchimento, tooltip e divisao interna discreta.
    addPolygons(
      fillColor        = ~COR_AREA,
      color            = "#B8B8B8",
      weight           = 0.5,
      opacity          = 0.8,
      fillOpacity      = 0.6,
      label            = cidades_tooltip,
      # sticky = FALSE e bringToFront = FALSE evitam o tooltip "travado" na tela:
      # bringToFront reordena o SVG do poligono no hover, e ao mover o mouse rapido
      # entre poligonos vizinhos isso confunde o mouseout do Leaflet e o antigo
      # tooltip fica "preso" (parece um bug nativo do Windows, mas eh do Leaflet)
      labelOptions     = labelOptions(sticky = FALSE, direction = "auto"),
      highlightOptions = highlightOptions(weight = 1, bringToFront = FALSE)
    ) %>%
    # Camada superior: contornos externos coloridos por faixa de distancia.
    addPolygons(
      data         = contornos_borda_sf,
      fill         = FALSE,
      color        = ~COR_BORDA,
      weight       = 2.5,
      opacity      = 1,
      smoothFactor = 0,
      options      = pathOptions(interactive = FALSE)
    ) %>%
    addLegend(
      position = "bottomleft",
      title    = "Cobertura",
      colors   = c(cor_area_100, cor_area_75, cor_area_55, cor_area_0_m, cor_area_0),
      labels   = c(">= 100%", ">= 75% < 100%", ">= 55% < 75%", "> 0% < 55%", "= 0% (Sem cobertura)")
    )

  if (!sem_distancia) {
    mapa_com <- mapa_com %>%
      addLegend(
        position = "bottomleft",
        title    = rotulo_distancia,
        colors   = c(cor_borda_sede, cor_borda_75, cor_borda_150, cor_borda_150_m, cor_borda_200, cor_borda_na),
        labels   = c(rotulo_dist_zero, "Até 75 km", "De 75 km a 150 km", "Acima de 150 km", "+200 km Longa distância", "Sem distância cadastrada")
      )
  }

  mapa_com <- mapa_com %>%
    addControl(
      position  = "bottomright",
      className = "info",
      html = tags$div(
        style = "width: 480px;",
        tags$div(
          style = glue("background: {cor_icone_card}; color: white; font-weight: bold; padding: 4px 9px; border-radius: 4px 4px 0 0; display: inline-block; font-size: 12px;"),
          "Cobertura Potencial"
        ),
        grafico_cobertura
      )
    ) %>%
    htmlwidgets::onRender("
    function(el, x) {
      this.zoomControl.setPosition('topright');

      // O .leaflet-map-pane tem transform: translate3d(...) que cria um stacking
      // context isolado: qualquer z-index dentro dele (inclusive tooltip-pane em
      // z-index 650) nunca supera elementos externos como o absolutePanel de cards.
      // Solucao: mover o painelTooltip para filho direto do leaflet-container
      // (fora do painelMapa), sincronizando o transform para que o posicionamento
      // dos tooltips continue correto.
      const mapaLeaflet    = this;
      const painelMapa     = el.querySelector('.leaflet-map-pane');
      const painelTooltip  = el.querySelector('.leaflet-tooltip-pane');

      if (painelMapa && painelTooltip) {
        el.appendChild(painelTooltip);
        painelTooltip.style.position      = 'absolute';
        painelTooltip.style.top           = '0';
        painelTooltip.style.left          = '0';
        painelTooltip.style.width         = '100%';
        painelTooltip.style.height        = '100%';
        painelTooltip.style.zIndex        = '1500';
        painelTooltip.style.pointerEvents = 'none';

        const sincronizarTransform = () => {
          painelTooltip.style.transform = painelMapa.style.transform;
        };

        mapaLeaflet.on('move zoom viewreset', sincronizarTransform);
        sincronizarTransform();
      }
    }
  ")

  # Limpeza das variaveis auxiliares que nao fazem parte do retorno -----------

  rm(
    cor_borda_sede, cor_borda_75, cor_borda_150, cor_borda_150_m, cor_borda_200, cor_borda_na, cor_borda_padrao,
    sem_distancia, sql_cor_borda,
    dist_fabrica, coluna_distancia, rotulo_distancia, rotulo_dist_zero,
    cor_area_100, cor_area_75, cor_area_55, cor_area_0_m, cor_area_0,
    cor_icone_card, cor_texto_card, cor_texto_card2, cor_texto_card3,
    fator_MAR, fator, eh_especial, coluna_marca,
    filtro_produto, filtro_sql_in, filtro_porte_c, filtro_porte_cc,
    data_mes_atual, meses_historico, meses_in,
    query_venda, query_cid, query_cli, query_cob,
    query_cob_hist, query_venda_hist, query_cli_hist,
    cli_cid, venda_cid,
    meses_pt, mes_ano_label, grafico_cob_df, cob_pot_hist_js,
    grafico_cob_opts, grafico_cobertura,
    parse_geojson_geom, cidades_geo, cidades_sf, contornos_borda_sf, ordem_borda,
    mapa_tooltip, cidades_tooltip, mapa_card,
    historico_cid, clientes, populacao, potencial, volume_hl, qtd_umb, fat_hab,
    cobertura_atual, cob_pot, perc_cli_ativo, mun_amarelo, cob_amarelo,
    cob_hist, cli_hist, cob_cli_hist, cob_pot_hist
  )

  return(list(
    mapa_potencial   = mapa_com,
    cards            = cards_topo,
    venda            = venda,
    cidades          = cidades,
    clientes_ativos  = clientes_ativos,
    clientes_inativos= clientes_inativos,
    cobertura        = cobertura,
    cob_hist_cid     = cob_hist_cid,
    venda_hist_cid   = venda_hist_cid,
    cli_hist_cid     = cli_hist_cid
  ))
}

saiba_mais_cli = function(mapa_pot){
  
  # DISTANCIA ja vem de mapa_pot$cidades na base escolhida no botao
  # Revenda/Fabrica (query_cid seleciona DIST_SEDE ou DIST_FAB como DISTANCIA),
  # entao a coluna aqui acompanha o botao sem precisar de logica propria
  cidades = mapa_pot$cidades[,c("COD_IBGE","CIDADE","DISTANCIA","POPULACAO","CLI_ATIVO","POTENCIAL","VOLUME_HL","QTD_UMB","POT_PROX_NVL","QTD_PDV","COB_POT","COR_POT_PROX_NVL", "COR_AREA","FAT_HAB")]
  cidades$PERC_CLI_ATIVO = round(cidades$QTD_PDV / cidades$CLI_ATIVO, 4) * 100
  cidades$PERC_CLI_POT_75 = round(cidades$QTD_PDV / cidades$POTENCIAL * 0.75, 4) * 100
  cidades$POT_CRESC = cidades$POTENCIAL - cidades$CLI_ATIVO
  cidades$COR_PERC_CLI_ATIVO = ifelse(cidades$PERC_CLI_ATIVO > 0 & cidades$PERC_CLI_ATIVO <= 55, "#FF0000",
                                      ifelse(cidades$PERC_CLI_ATIVO > 55 & cidades$PERC_CLI_ATIVO < 75, "#be9c00", "#006400"))
  cidades$POPULACAO = ifelse(cidades$POPULACAO <= 0, NA, cidades$POPULACAO)
  cidades$CLI_ATIVO = ifelse(cidades$CLI_ATIVO <= 0, NA, cidades$CLI_ATIVO)
  cidades$POTENCIAL = ifelse(cidades$POTENCIAL <= 0, NA, cidades$POTENCIAL)
  cidades$POT_CRESC = ifelse(cidades$POT_CRESC <= 0, NA, cidades$POT_CRESC)
  cidades$VOLUME_HL = ifelse(cidades$VOLUME_HL <= 0, NA, cidades$VOLUME_HL)
  cidades$QTD_UMB = ifelse(cidades$QTD_UMB <= 0, NA, cidades$QTD_UMB)
  cidades$QTD_PDV = ifelse(cidades$QTD_PDV <= 0, NA, cidades$QTD_PDV)
  cidades$PERC_CLI_POT_75 = ifelse(cidades$PERC_CLI_POT_75 <= 0, NA, cidades$PERC_CLI_POT_75)
  cidades$POT_PROX_NVL = ifelse(cidades$POT_PROX_NVL <= 0, NA, cidades$POT_PROX_NVL)
  cidades$PERC_CLI_ATIVO = ifelse(cidades$PERC_CLI_ATIVO <= 0, NA, cidades$PERC_CLI_ATIVO)
  cidades$COB_POT = ifelse(cidades$COB_POT <= 0, NA, cidades$COB_POT)
  cidades$FAT_HAB = ifelse(cidades$FAT_HAB <= 0, NA, cidades$FAT_HAB)
  
  cidades |>
    select(
      COD_IBGE, COR_POT_PROX_NVL, COR_AREA, COR_PERC_CLI_ATIVO,
      CIDADE, DISTANCIA, POPULACAO, CLI_ATIVO, POTENCIAL, PERC_CLI_POT_75, POT_CRESC,
      VOLUME_HL, QTD_UMB, QTD_PDV,
      POT_PROX_NVL, PERC_CLI_ATIVO, COB_POT, FAT_HAB
    )
}


ruptura_6m = function(mapa_pot){
  
  cli_ativos = mapa_pot$clientes_ativos
  cli_ativos_6m_s_compra = cli_ativos |> filter(ULTIMA_COMPRA <= as.character(format(Sys.Date() %m-% months(6), "%Y%m%d"))) |>
    select(CLI_ATIVO, NOME, FANTASIA, MUNICIPIO, ENDERECO, PORTE, CANAL, VEN, TITULO_ABERTO, POSSUI_CEV, SUBEMPRESA, ULTIMA_COMPRA)
  cli_ativos_6m_s_compra$POSSUI_CEV = ifelse(cli_ativos_6m_s_compra$POSSUI_CEV == "SIM", "Sim", "Não")
  cli_ativos_6m_s_compra$TITULO_ABERTO = ifelse(cli_ativos_6m_s_compra$TITULO_ABERTO == "SIM", "Sim", "Não")
  cli_ativos_6m_s_compra$PESQUISA_CLI = paste0(cli_ativos_6m_s_compra$CLI_ATIVO, cli_ativos_6m_s_compra$NOME, cli_ativos_6m_s_compra$FANTASIA, collapse = "|")
  cli_ativos_6m_s_compra$ULTIMA_COMPRA = as.Date(cli_ativos_6m_s_compra$ULTIMA_COMPRA, format = "%Y%m%d")

  return(cli_ativos_6m_s_compra)
}


clientes_inativos = function(mapa_pot){
  
  cli_inativos = mapa_pot$clientes_inativos |> select(CLI_ATIVO, NOME, FANTASIA, MUNICIPIO, ENDERECO, PORTE, CANAL, TITULO_ABERTO, POSSUI_CEV, SUBEMPRESA, ULTIMA_COMPRA)
  cli_inativos$POSSUI_CEV = ifelse(cli_inativos$POSSUI_CEV == "SIM", "Sim", "Não")
  cli_inativos$TITULO_ABERTO = ifelse(cli_inativos$TITULO_ABERTO == "SIM", "Sim", "Não")
  cli_inativos$PESQUISA_CLI = paste0(cli_inativos$CLI_ATIVO, cli_inativos$NOME, cli_inativos$FANTASIA, collapse = "|")
  cli_inativos$ULTIMA_COMPRA = as.Date(cli_inativos$ULTIMA_COMPRA, format = "%Y%m%d")

  return(cli_inativos)
}
