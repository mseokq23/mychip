# KLayout startup macro used by klayout-etri (scripts/etri050-env.sh):
#   klayout -l <ETRI .lyp> -rm etri_view.rb [files...]
# Opened layouts show every hierarchy level. KLayout's default draws only the
# top cell, so an array of transistor cells would look like empty frames.
app = RBA::Application.instance
app.set_config("full-hierarchy-new-cell", "true")
app.commit_config
