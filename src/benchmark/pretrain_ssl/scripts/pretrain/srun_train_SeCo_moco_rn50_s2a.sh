#!/usr/bin/env bash

# slurm job configuration
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --ntasks-per-node=4
#SBATCH --output=srun_outputs/B12_train_SeCo_moco_rn50_%j.out
#SBATCH --error=srun_outputs/B12_train_SeCo_moco_rn50_%j.err
#SBATCH --time=23:00:00
#SBATCH --job-name=pretrain_moco_rn50
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=10
#SBATCH --partition=booster

export SRUN_CPUS_PER_TASK=${SLURM_CPUS_PER_TASK}

master_node=${SLURM_NODELIST:0:9}${SLURM_NODELIST:10:4}
dist_url="tcp://"
dist_url+=$master_node
dist_url+=:40000


# load required modules
module load Stages/2022
module load GCCcore/.11.2.0
module load Python

# activate virtual environment
source /p/project/hai_dm4eo/wang_yi/env2/bin/activate

# define available gpus
export CUDA_VISIBLE_DEVICES=0,1,2,3

# run script as slurm job
srun python -u pretrain_moco_v2_seco_ms.py \
--is_slurm_job \
--data /p/project/hai_ssl4eo/wang_yi/data/seco/seco_1s_uint8.lmdb \
--checkpoints /p/project/hai_ssl4eo/wang_yi/SSL4EO-S12/src/benchmark/pretrain_ssl/checkpoints/moco/SeCo_B12_rn50_224 \
--bands B12 \
--lmdb \
--arch resnet50 \
--workers 8 \
--batch-size 64 \
--epochs 100 \
--lr 0.03 \
--mlp \
--moco-t 0.2 \
--aug-plus \
--cos \
--dist-url $dist_url \
--dist-backend 'nccl' \
--seed 42 \
--mode s2a \
--dtype uint8 \
--season augment \
--in_size 224 \
#--resume /p/project/hai_ssl4eo/wang_yi/SSL4EO-S12/src/benchmark/pretrain_ssl/checkpoints/moco/SEN12MS_B13_rn50_224/checkpoint_0029.pth.tar