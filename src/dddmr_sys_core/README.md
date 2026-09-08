# dddmr_sys_core

This package vendors the public ROS 2 interfaces and enum core used by
`dfl-rlab/dddmr_navigation` commit
`1d0367376380205a6a18c0ad7c7c16c9338c96bc`.

It is included so the M20Pro Foxy runtime can build and import
`dddmr_sys_core.action.PToPMoveBase` without installing the full DDDMR algorithm
stack inside the production workspace.

This package does not provide a DDDMR planner, mapper, local planner, or
`/p2p_move_base` action server. Those runtime components must still be supplied
by the adapted DDDMR deployment.
