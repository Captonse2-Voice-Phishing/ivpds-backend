-- What the Risk Engine based its score on, so a stored result can be traced back to the exact model and rules.
alter table risk_results
    add column model_probability   numeric(7, 6),
    add column nlp_model_version   varchar(100),
    add column ruleset_version     varchar(30),
    add column risk_engine_version varchar(30),
    add constraint ck_risk_results_model_probability check (model_probability between 0 and 1);

-- A call can have many analyses over time, but only one that is still waiting or running.
create unique index uq_analyses_active_call on analyses (call_record_id)
    where status in ('PENDING', 'PROCESSING');
