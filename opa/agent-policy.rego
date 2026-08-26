package agent.policy

deny contains msg if {
  not input.agent.id
  msg := "agent.id is required"
}

deny contains msg if {
  contains(input.agent.id, "{{")
  msg := "agent.id still contains placeholder"
}

deny contains msg if {
  not input.agent.team
  msg := "agent.team is required"
}

deny contains msg if {
  contains(input.agent.team, "{{")
  msg := "agent.team still contains placeholder"
}

deny contains msg if {
  not input.identity.sp_client_id
  msg := "identity.sp_client_id is required"
}

deny contains msg if {
  contains(input.identity.sp_client_id, "{{")
  msg := "identity.sp_client_id still contains placeholder"
}

deny contains msg if {
  not input.identity.keyvault_url
  msg := "identity.keyvault_url is required"
}

deny contains msg if {
  contains(input.identity.keyvault_url, "{{")
  msg := "identity.keyvault_url still contains placeholder"
}

deny contains msg if {
  not input.evaluation.ci_gate == true
  msg := "evaluation.ci_gate must be true"
}

deny contains msg if {
  input.evaluation.pass_threshold < 0.95
  msg := "evaluation.pass_threshold must be >= 0.95"
}

deny contains msg if {
  not input.prompts.active_version
  msg := "prompts.active_version is required"
}

deny contains msg if {
  not input.prompts.source
  msg := "prompts.source is required"
}