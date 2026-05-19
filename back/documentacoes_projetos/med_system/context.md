# MedSystem - Contexto de Produto para Agentes e Times Externos

## Objetivo deste documento
Este documento descreve a proposta do sistema (o problema que ele resolve e para quem), com base no código e na documentação existente.

Regra de validação aplicada em cada afirmação:
- does the project do this, or its expected to do this?

Quando não foi possível confirmar pelo código, o item foi marcado como **Needs investigation**.

## Escopo analisado
- `docs/`
- landing page (`MedSystem_front/pages/LandingPage.tsx`)
- frontend e backend (`MedSystem_front/*`, `MedSystem_back/src/*`)

## Proposição central do MedSystem
O MedSystem é uma plataforma de operação clínica que tenta reduzir perda de tempo na consulta e retrabalho administrativo, organizando a jornada em um fluxo contínuo:

Recepção/agendamento -> triagem -> consulta/prontuário -> apoio clínico por IA -> documentos -> resumo -> histórico.

Em termos de produto, ele combina:
- Registro clínico e persistência de dados da consulta.
- Assistência por IA para apoiar (não substituir) decisão clínica.
- Geração/impressão de documentos assistenciais no mesmo fluxo.
- Continuidade do cuidado com histórico e contexto do paciente.
- Operação de clínica além do atendimento (agenda, CRM/WhatsApp, financeiro, permissões).

## Dores que o sistema tenta resolver
### 1. Consulta fragmentada em múltiplas telas e passos manuais
Como o sistema responde:
- Fluxo único com módulos clínicos e documentos na mesma jornada.
- Persistência de consulta, triagem, prontuário gerado e resumo.

Status: **Implementado**

### 2. Retrabalho para produzir documentação clínica no fim do atendimento
Como o sistema responde:
- APIs e componentes para geração/sugestão de receituário, exames, atestado e encaminhamento.
- Serviço de impressão e geração de HTML/PDF para documentos.

Status: **Implementado**

### 3. Falta de continuidade clínica por histórico de difícil acesso
Como o sistema responde:
- Histórico de consultas por paciente com filtro de finalizadas.
- Histórico integrado ao contexto da consulta.

Status: **Implementado**

### 4. Risco de erro por sobrecarga cognitiva do profissional
Como o sistema responde:
- Apoio à decisão com hipóteses, red flags, sugestões por seção e revalidação.
- Alertas relacionados a medicação/interação no fluxo de documentos.

Status: **Implementado (parcialmente dependente de configuração e qualidade do input)**

### 5. Falta de controle operacional da clínica fora do ato clínico
Como o sistema responde:
- Agenda e fila (incluindo senha de recepção).
- CRM/WhatsApp com webhook, roteamento e handoff humano/bot.
- Financeiro (receitas, despesas, pagamentos e anexos).

Status: **Implementado**

## O que está validado no código (resumo executivo)
- Backend expõe domínios clínicos e operacionais via rotas dedicadas (consultas, triagens, IA, agenda, CRM, financeiro, permissões, preferências, assinaturas).
- Consulta possui regras de edição e ownership (incluindo janela de edição de consulta finalizada no mesmo dia).
- Multi-instituição e restrição por profissão aparecem na lógica de acesso e em consultas SQL.
- IA possui endpoints para prontuário, sugestões clínicas, documentos, resumo e transcrição de áudio (AssemblyAI), incluindo timeout e polling.
- Landing page e página de funcionalidades refletem essa narrativa de fluxo clínico assistido.

## FAQ para agentes e times externos

### 1) O MedSystem é só prontuário eletrônico?
Resposta curta: não.
- Além do prontuário/consulta, há agenda, triagem, histórico, IA clínica, documentos, CRM/WhatsApp e financeiro.

Status: **Implementado**

Validação: does the project do this, or its expected to do this?
- **Faz hoje** (múltiplos módulos e rotas no backend e dashboards no front).

### 2) A IA toma decisão médica automaticamente?
Resposta curta: não.
- O prompt mestre e textos de produto posicionam IA como apoio.
- Decisão final permanece com o profissional.

Status: **Implementado como diretriz de produto/prompt; Needs investigation para enforcement formal em todos os fluxos**

Validação: does the project do this, or its expected to do this?
- **Parcial**: o comportamento esperado está explícito em prompt e copy; precisa auditoria de ponta a ponta para garantir enforcement em todos os endpoints.

### 3) O sistema realmente persiste o que foi feito na consulta?
Resposta curta: sim, com ressalvas de concorrência já tratadas em parte.
- Consulta e documentos são persistidos; há rota unificada para salvar documentos e reduzir race condition.

Status: **Implementado**

Validação: does the project do this, or its expected to do this?
- **Faz hoje**.

### 4) O histórico do paciente é reaproveitado na continuidade do cuidado?
Resposta curta: sim.
- Há endpoint de histórico por paciente e ordenação por finalização/criação.

Status: **Implementado**

Validação: does the project do this, or its expected to do this?
- **Faz hoje**.

### 5) É possível operar em mobile sem app nativo?
Resposta curta: sim para fluxos específicos.
- Existem rotas e páginas públicas para captura/microfone mobile por token de sessão.

Status: **Implementado (escopo específico)**

Validação: does the project do this, or its expected to do this?
- **Faz hoje** em fluxos mobile dedicados.

### 6) O produto cobre apenas clínica ou também operação administrativa?
Resposta curta: cobre os dois.
- Módulos administrativos: usuários/permissões, convites, receitas/despesas, pagamentos, CRM.

Status: **Implementado**

Validação: does the project do this, or its expected to do this?
- **Faz hoje**.

### 7) O produto já está preparado para cenários multi-tenant?
Resposta curta: sim, em diversas rotas e regras de acesso.
- Instituição e profissão são usados para restringir leitura/escrita em vários domínios.

Status: **Implementado (com potencial de inconsistência entre módulos)**

Validação: does the project do this, or its expected to do this?
- **Faz hoje**, porém recomenda-se auditoria completa para cobertura homogênea.

## Mapa "landing claim" vs implementação
- "Atendimento organizado de ponta a ponta": **Implementado**.
- "Resumo com IA ao encerrar atendimento": **Implementado**.
- "Documentos prontos para imprimir": **Implementado**.
- "Histórico completo do paciente": **Implementado**.
- "Segurança/LGPD total": **Implementado** 

## Conclusão prática para agentes
Se você for um agente externo integrando ou evoluindo o MedSystem, pense nele como:
- Plataforma clínica orientada a fluxo.
- Componente de IA assistiva acoplada ao prontuário e documentação.
- Produto também operacional (agenda, CRM e financeiro), não apenas clínico.

Checklist mental recomendado para qualquer nova mudança:
1. Isso reduz ou aumenta retrabalho da equipe clínica?
2. Isso preserva continuidade do cuidado (histórico/contexto)?
3. Isso respeita fronteiras de instituição/papel?
4. Isso mantém IA como apoio e não substituição da decisão profissional?
5. Isso confirma "faz hoje" ou só "esperado"?
