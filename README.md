# Radar Futebol 6.0 — piloto gratuito por navegador

Um **protótipo independente** de apoio jornalístico para futebol profissional masculino. Seu objetivo é encontrar manchetes relevantes nos **sites institucionais** dos clubes e seleções, guardá-las em um feed simples e permitir que você consulte a fonte original rapidamente. Não é um produto da ESPN, dos clubes ou de federações.

**Estado: pronto para configurar e testar, ainda NÃO publicado nem validado contra as fontes ao vivo.** O ambiente de construção não tem acesso HTTP externo, por isso os endereços foram pesquisados na web, mas a coleta precisa ser verificada na sua conta do GitHub Actions. Não utilize como fonte única para o Bottom Line.

## Por que esta arquitetura

- **GitHub Pages (gratuito)**: publica somente os arquivos estáticos de `docs/`, acessíveis em casa ou no trabalho. Repositório **público** é necessário no plano GitHub Free. A interface é protegida por login Supabase, não pela privacidade do repositório.
- **GitHub Actions (agendamento)**: consulta as nove fontes oficiais cadastradas a cada ~30 minutos; pode atrasar, falhar ou ser desativado após 60 dias de inatividade do repositório público. Não promete cobertura completa nem atualização em tempo real.
- **Supabase Free**: guarda notícias, últimas coletas, favoritos e preferências. Pode pausar após uma semana de pouca atividade e possui cotas. RLS protege dados e o painel exige Supabase Auth.
- **Sem servidor permanente e sem token do X**: esta fase não utiliza API paga do X. Links do ge e da ESPN ficam como atalhos externos para cruzamento de informação; não entram automaticamente no feed.

## 1. Prévia imediata

Abra `docs/demo.html` no navegador. As manchetes da prévia são **fictícias e visivelmente marcadas**; demonstra filtros, salvos e alertas sem conectar a nenhum serviço.

## 2. Crie o banco de dados gratuito

1. Cadastre-se em https://supabase.com e crie um projeto **Free**.
2. Em **SQL Editor**, cole o conteúdo integral de `schema.sql` e execute.
3. Em **Authentication > Users**, crie um usuário para você usando e-mail e senha. Se seu projeto permitir cadastro público, **desative a opção de novos cadastros** (o piloto foi pensado para um usuário).
4. Copie a **Project URL** e a **publishable key (ou anon key legada)** do Supabase e substitua apenas os campos correspondentes em `docs/config.js`.
5. A **service_role key** é um segredo administrativo: **NUNCA** a coloque em `docs/`, em `config.js`, no código do navegador ou em commits. Ela será usada apenas nos GitHub Actions Secrets.

## 3. Publique o site no GitHub Pages

1. Crie um **repositório público** no GitHub e adicione todo o conteúdo desta pasta, preservando `.github/workflows/coletar.yml`.
2. Em **Settings > Pages**, selecione **Deploy from a branch**: `main`, pasta `/docs`, e salve. Se a branch for diferente, selecione-a.
3. O GitHub apresentará um endereço semelhante a `https://SEU-USUARIO.github.io/NOME-DO-REPOSITORIO/`. **O endereço real só existe depois que você publicar**.
4. Em **Settings > Secrets and variables > Actions > New repository secret**, crie `SUPABASE_URL` (URL do projeto) e `SUPABASE_SERVICE_ROLE_KEY` (chave de administração, somente segredo).
5. Acesse a guia **Actions > Coletar manchetes oficiais > Run workflow** para disparar a primeira coleta manualmente. Acompanhe logs individuais de cada fonte; nunca exponha o token administrativo em comentários ou capturas.
6. Abra a URL do Pages, entre com e-mail e senha do Supabase. Os favoritos e preferências ficam no banco e aparecem em outro computador após novo login.

**Recomendação de segurança:** use senha forte, encerre a sessão em computadores compartilhados e, se disponível, ative MFA. `sessionStorage` do navegador mantém a sessão só naquela aba/sessão; você pode entrar novamente em cada computador.

## 4. O que o monitor coleta

Fontes iniciais em `pilot_sources.json`:

- Corinthians — https://www.corinthians.com.br/noticias
- Palmeiras — https://www.palmeiras.com.br/noticias/
- Flamengo — https://www.flamengo.com.br/noticias/futebol
- São Paulo — https://www.saopaulofc.net/esporte/futebol-masculino-profissional/
- Arsenal — https://www.arsenal.com/news
- Liverpool — https://www.liverpoolfc.com/news?categoryId=first-team&type=news
- Chelsea — https://www.chelseafc.com/en/news
- Manchester City — https://www.mancity.com/news
- CBF / Seleção Brasileira — https://www.cbf.com.br/selecao-brasileira/noticias/selecao-masculina

As 130 equipes do catálogo anterior continuam cadastradas, mas as **outras 121 estão fora do piloto** e aparecem desabilitadas para não sugerir cobertura inexistente.

O coletor tenta ler links de manchetes, descarta temas de feminino, base, outros esportes e expressões claramente especulativas, identifica categorias prioritárias e ignora publicações com data identificável superior a 21 dias. Se a data não puder ser identificada, o título fica com **data de publicação não validada**, e a data de detecção não deve ser interpretada como publicação. Sites que exigem JavaScript ou bloqueiam robôs podem produzir zero links. Não interpreta textos completos nem autentica cada detalhe.

O feed só mostra links de domínios configurados; **origem reconhecida não dispensa leitura do comunicado antes de ir ao ar**. Seu feedback de relevância (salvar/ocultar) não altera o status de confiabilidade.

## 5. Notificações e tradução

- Configuração de alertas: discreto (padrão), destaque visual, visual com som e desligado.
- Os alertas funcionam **somente com a aba aberta** e detectam itens novos após uma sincronização; o som pode depender de interação do usuário. Não são notificações push.
- As notícias em inglês têm atalho **Traduzir página**, que tenta abrir a fonte no Google Tradutor em português, em outra aba. Essa tradução pode falhar, não é integrada ao feed e **ainda exige conferência**. Tradução automática dos títulos dentro do painel é etapa futura.

## 6. Diagnóstico e métricas dos primeiros testes

Abra **Estado das fontes** e confira horários de consulta e falhas. Compare diariamente com os canais oficiais abertos manualmente; anote anúncios importantes ausentes, atrasos, links duplicados e manchetes irrelevantes. O painel considera “respondendo” o retorno da página, **não** a certeza de cobertura.

Use por **10 a 15 dias** antes de ampliá-lo. Comece verificando pelo menos um comunicado real por clube e sua data, e se as chamadas no GitHub Actions estão concluindo com sucesso.

### Testes locais, sem internet

```bash
python -m unittest discover -s tests -v
node --check docs/app.js
node --check docs/cloud-api.js
```

O coletor pode ser executado manualmente em `--dry-run` **em uma máquina com internet**, sem salvar nada: `python collect.py --dry-run`. **Não será possível avaliar se uma fonte funciona com base apenas nos testes de fixtures.**

### Estimativa de custo nesta etapa

Pode operar nos planos gratuitos do GitHub e Supabase, **desde que permaneça dentro das cotas**. Nenhum pagamento ou upgrade é configurado por este projeto. Se precisar coletar dezenas de sites com maior frequência, será necessário reavaliar cotas, bloqueios e confiabilidade.

## Observações importantes

- O conteúdo do repositório público é visível para qualquer pessoa; **nenhuma senha ou chave administrativa deve ser publicada**.
- Evite scraping agressivo; respeite os limites e as regras de acesso de cada site e use apenas links/pequenos títulos, sem republicar integralmente textos protegidos.
- Supabase Auth com login e RLS protege preferências e leitura do feed, mas esta implementação ainda requer uma auditoria de segurança e testes reais antes de uso intensivo.
- O projeto não se conecta à conta do X, não usa fontes em tempo real e não promete identificar 100% dos comunicados.

## Referências para instalação

- https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://supabase.com/docs/guides/database/postgres/row-level-security
- https://supabase.com/docs/guides/api
