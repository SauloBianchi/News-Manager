# Observações do projeto — NewsManager

Registro de tarefas, decisões, problemas e pendências. (Este arquivo não existia no zip recebido; foi criado
agora com as entradas desta etapa — acrescente as das etapas anteriores se tiver anotações.)

## Tarefas

| # | Tarefa | Estado |
|---|---|---|
| T-01 | Previsão do tempo: serviço, cache e alertas (`app/tempo.py`) | feito, testado offline |
| T-02 | Faixa superior com `CIDADE • temp condição`, atualização em segundo plano | feito; **falta conferir na janela real** |
| T-03 | Tela maior "Previsão do Tempo" + gráfico de 24 h | feito; **falta conferir na janela real** |
| T-04 | Cidade por usuário (tela e Perfil), localização por IP com consentimento | feito; **falta conferir na janela real** |
| T-05 | Catálogo de fontes + parser RSS/Atom seguro (`config/fontes_noticias.json`, `app/feeds.py`) | feito, testado offline |
| T-06 | Serviço de clipping (coleta, filtros, deduplicação, importação, salvas, histórico) | feito, testado offline (SQLite) |
| T-07 | Tela Clipping (busca, prévia, importar, salvas, histórico, fontes) | feito; **falta conferir na janela real** |
| T-08 | Importação automática 1×/dia ao abrir | feito; **falta conferir na janela real** |
| T-09 | Testes (`tests/`), seed (verificações offline e `--verificar-rede`), documentação | feito |
| T-10 | (Opcional) Criar pauta do tempo | feito |

## Decisões

- **Rede só em thread, banco só na thread principal.** A conexão MySQL é única e não é segura entre threads;
  por isso a coleta é dividida em 3 passos (banco → rede em thread → banco) e `app/segundo_plano.py` devolve o
  resultado pela fila + `after()`.
- **Sem dependências novas.** Parser XML da biblioteca padrão com rejeição de `<!ENTITY>`/DOCTYPE com subconjunto
  interno (equivale ao que o defusedxml bloquearia); HTTP com o `requests` que já estava no projeto.
- **Open-Meteo** (sem chave) para previsão e cidades; **ipapi.co** para localização por IP (HTTPS, gratuito,
  ~1.000/dia) — só com consentimento, decisão guardada em `preferencias_usuario` (`localizacao_ip`).
- **Preferências de texto** (cidade) usam a mesma tabela `preferencias_usuario` (chaves `cidade_*`); o
  `PerfilService.preferencias()` continua devolvendo só os interruptores.
- **Itens do clipping ficam no banco** (`clipping_itens`); o banco serve de cache da coleta: dentro de 15 min a
  prévia vem dele, sem nova requisição. Itens não importados são apagados depois de 30 dias.
- **Importação nunca publica** (`rascunho`, `em_pauta` ou `revisao`); atribuição no texto e nos campos
  `fonte_*`; imagens nunca são baixadas.
- **Fontes não verificadas vêm desativadas.** Só G1 e Agência Brasil vêm ligadas (endereços vistos em diretório
  de terceiros, não na página oficial do jornal).
- `NoticiaService.criar` e `DatabaseManager.criar_noticia` ganharam parâmetros opcionais `fonte_*` (padrão
  `None`): o comportamento anterior não muda.
- Item novo no menu (**Clipping**) em `ITENS_NAVEGACAO`; a tela do tempo é interna (não aparece no menu).
- Criado um `.gitignore` (o zip recebido não tinha) que mantém fora do Git `config/client_secret.json`,
  `config/email_config.json` e `config/graficos.json`, mas **versiona** `config/fontes_noticias.json`.

## Problemas encontrados

- O zip recebido continha `config/client_secret.json` e `config/email_config.json` **reais**. Eles foram
  **excluídos** do zip entregue. Se esse zip circulou, considere trocar o segredo OAuth e a senha SMTP.
- Não havia `OBSERVACOES_DO_PROJETO.md` nem `.gitignore` no zip.
- `noticias.titulo` aceita 120 caracteres no serviço: títulos longos dos feeds são cortados com "…".

## Correções pós-entrega (bugs relatados no uso)

- **Buraco ao cancelar o formulário em Autores e Categorias:** a Frame que guarda o formulário mantinha o
  último tamanho ao perder o filho. Agora `_TelaBase._esconder_form` encolhe o contêiner e
  `RolagemVertical.ajustar()` recalcula a área rolável; `_exibir_form` leva o formulário para a vista.
- **EDITAR no cartão do feed "não funcionava":** carregava o editor rápido, que fica fora da vista. Agora abre
  o editor completo (`NoticiasFrame._editar_do_cartao`), o mesmo de "Modificar publicação".
- **Roda do mouse no editor de matéria rolava a página junto:** `RolagemVertical._rolar` não move mais a página
  quando o ponteiro está sobre um Text/Listbox que ainda pode rolar naquele sentido (ao chegar no fim do texto,
  a página volta a rolar).
- Esses ajustes foram checados por teste de lógica (Tk falso); o efeito visual precisa ser conferido na janela real.

## Pendências / não testado ao vivo

- **Nenhuma chamada real à internet foi feita**: feeds, Open-Meteo, geocodificação e ipapi.co foram testados só
  com respostas simuladas. Rode `python seed.py --verificar-rede` (e `--com-ip`) na sua máquina.
- **Nenhuma janela Tk real foi aberta**: as telas foram exercitadas com um Tk de mentira
  (`tests/_tkfalso.py`). Aparência, rolagem, foco, cursor de mão e eventos precisam ser conferidos pelo
  `ROTEIRO_DE_TESTE.md` (seções 10 e 11).
- **MySQL/MariaDB real não foi usado**: os serviços rodaram em SQLite em memória; o SQL específico (ex.:
  `INSERT IGNORE`, DDL das tabelas novas) deve ser conferido com `python seed.py --verificar`.
- Os endereços de feed marcados `nao_verificada` podem estar errados ou descontinuados. Estadão, UOL, Correio do
  Povo e GZH ficaram sem feed (usar "Adicionar feed próprio").
- As fixtures RSS/Atom são sintéticas (estrutura real, conteúdo fictício) porque não havia internet.
- Termos de uso de cada jornal não foram lidos um a um: a tela avisa para conferi-los.
- Ideias: filtro de feeds por país/idioma na tela; API de notícias opcional (GNews/NewsData.io) com chave em
  `config/`; botão para "marcar item como descartado".
